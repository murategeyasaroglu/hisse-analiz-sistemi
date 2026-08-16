"""Hibrit analiz motoru — math_engine + Claude API niteliksel derleme."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional, Protocol

from analiz_motoru_system_prompt import ANALYSIS_ENGINE_SYSTEM_PROMPT
from analysis_schemas import HisseEtkiSkoruOutput, QualitativeAnalysis
from math_engine import (
    MIN_REGULATORY_CAR_DEFAULT,
    NPL_WARNING_THRESHOLD_DEFAULT,
    compute_math_precompute,
    get_sector_model_type,
)
from schemas import InputSchema
import labels

DEFAULT_MODEL = "claude-sonnet-4-20250514"
JSON_PREFILL = "{"

# Streamlit ve diğer entegrasyonlar için desteklenen açık modül API'si.
__all__ = ["Analyzer", "analyze_company", "run_analysis"]


class ClaudeClientProtocol(Protocol):
    def create_message(self, **kwargs: Any) -> Any: ...


class Analyzer:
    """
    INPUT_SCHEMA alır, math_engine ile ön hesaplar,
    Claude API ile niteliksel analiz + nihai JSON üretir.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        client: Optional[ClaudeClientProtocol] = None,
        use_local_fallback: bool = False,
    ) -> None:
        self.model = model
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._client = client
        self._use_local_fallback = use_local_fallback

        if self._client is None and not self._use_local_fallback:
            if not self._api_key:
                self._use_local_fallback = True
            else:
                self._client = _build_anthropic_client(self._api_key)

    def analyze(
        self,
        input_data: InputSchema,
        kap_metni: Optional[str] = None,
    ) -> HisseEtkiSkoruOutput:
        math_result = compute_math_precompute(input_data)

        if self._use_local_fallback:
            return _local_qualitative_compile(input_data, math_result, kap_metni)

        user_payload = {
            "input_schema": input_data.model_dump(mode="json"),
            "math_precompute": math_result.model_dump(mode="json"),
            "kap_metni": kap_metni,
        }
        user_message = (
            "Aşağıdaki verilerle Hisse Etki Skoru JSON çıktısını üret:\n\n"
            + json.dumps(user_payload, ensure_ascii=False, indent=2)
        )

        raw_json = self._call_claude(user_message, math_result)
        parsed = json.loads(raw_json)
        result = HisseEtkiSkoruOutput.model_validate(parsed)
        return _apply_domain_rules_and_reasoning(result, input_data, kap_metni)

    def _call_claude(self, user_message: str, math_result: Any) -> str:
        assert self._client is not None

        response = self._client.create_message(
            model=self.model,
            max_tokens=4096,
            temperature=0,
            system=ANALYSIS_ENGINE_SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": JSON_PREFILL},
            ],
        )

        continuation = _extract_text(response)
        full_json = JSON_PREFILL + continuation
        _ensure_valid_json(full_json)
        return full_json


def analyze_company(
    input_data: InputSchema,
    kap_metni: Optional[str] = None,
    *,
    use_local_fallback: bool = False,
) -> HisseEtkiSkoruOutput:
    """Kısa yol fonksiyonu."""
    return Analyzer(use_local_fallback=use_local_fallback).analyze(
        input_data, kap_metni=kap_metni
    )


def _run_live_analysis(company_payload: dict[str, Any]) -> dict[str, Any]:
    """Canlı Yahoo payload'ı için API gerektirmeyen hızlı analiz yolu."""
    identifier = company_payload.get("company_identifier", {})
    financials = company_payload.get("financials", {})
    events = company_payload.get("qualitative_events", [])
    sector_code = identifier.get("sector_code")
    model_type = get_sector_model_type(sector_code)
    sub_scores = _live_sub_scores(financials, model_type)
    quantitative_score = sum(sub_scores.values()) / len(sub_scores) if sub_scores else 50.0
    event_average = sum(float(event.get("event_score", 0)) for event in events) / len(events) if events else 0.0
    qualitative_score = max(0.0, min(100.0, 50.0 + event_average * 5.0))
    composite = quantitative_score * 0.70 + qualitative_score * 0.30
    red_flags: list[dict[str, str]] = []

    if model_type == "financial_institution":
        car = financials.get("sermaye_yeterlilik_orani")
        npl = financials.get("takipteki_krediler_orani")
        if car is not None and car < MIN_REGULATORY_CAR_DEFAULT:
            composite = min(composite, 15.0)
            red_flags.append({"trigger_condition": f"Sermaye yeterlilik oranı %{car:.2f} ile asgari referansın altında."})
        if npl is not None and npl > NPL_WARNING_THRESHOLD_DEFAULT:
            composite = min(composite, 30.0)
            red_flags.append({"trigger_condition": f"Takipteki krediler oranı %{npl:.2f} ile uyarı eşiğinin üzerinde."})

    recommendation = _score_to_recommendation(composite)
    driver_key, driver_score = _dominant_category(sub_scores)
    driver_label = labels.label_for(driver_key, model_type) if driver_key else "Kategori"
    if red_flags:
        reasoning = f"{red_flags[0]['trigger_condition']} Bu risk nihai skoru sınırlandırdı."
    else:
        direction = "olumlu katkı sağlıyor" if (driver_score or 50) >= 50 else "sonucu aşağı çekiyor"
        reasoning = f"{driver_label} ({driver_score:.0f}/100) {direction}."
    news_reasoning = _news_reasoning(events)
    if news_reasoning:
        reasoning += f"\n\n{news_reasoning}"

    return {
        "ticker": identifier.get("ticker"),
        "company_name": identifier.get("company_name"),
        "model_type": model_type,
        "quantitative": {"sub_scores": sub_scores, "raw_score_100": round(quantitative_score, 2)},
        "qualitative_events": events,
        "hisse_etki_skoru": round(composite, 2),
        "composite_score": round(composite, 2),
        "oneri": recommendation,
        "recommendation": recommendation,
        "recommendation_label": labels.recommendation_label(recommendation),
        "karar_gerekcesi": reasoning,
        "reasoning": reasoning,
        "red_flags": red_flags,
    }


def _live_sub_scores(financials: dict[str, Any], model_type: str) -> dict[str, float]:
    if model_type == "financial_institution":
        return {
            "net_interest_margin": _range_score(financials.get("net_faiz_marji"), 0, 10),
            "profitability_roe": _range_score(financials.get("roe"), 0, 30),
            "capital_adequacy": _range_score(financials.get("sermaye_yeterlilik_orani"), 8, 20),
            "asset_quality": _range_score(financials.get("takipteki_krediler_orani"), 10, 0),
        }
    return {
        "profitability": _average_scores(_range_score(financials.get("roe"), 0, 30), _range_score(financials.get("favok_marji"), -10, 30)),
        "leverage": _range_score(financials.get("net_borc_favok"), 6, 0),
        "valuation": _average_scores(_range_score(financials.get("f_k"), 35, 4), _range_score(financials.get("pd_dd"), 8, 0.5)),
        "growth_and_cash_quality": _range_score(financials.get("gelir_buyume_yoy"), -20, 40),
    }


def _range_score(value: Any, low: float, high: float) -> float:
    if value is None:
        return 50.0
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 50.0
    if high == low:
        return 50.0
    return max(0.0, min(100.0, (value - low) / (high - low) * 100))


def _average_scores(*scores: float) -> float:
    return sum(scores) / len(scores) if scores else 50.0


def _news_reasoning(events: list[dict[str, Any]]) -> str:
    """En yüksek etkili gerçek haberleri karar gerekçesine doğrudan bağlar."""
    real_events = [event for event in events if not event.get("is_placeholder")]
    if not real_events:
        return "Haber etkisi: Son yedi günde doğrulanmış yeni haber bulunamadığından haber bileşeni nötr (0/10) tutuldu."
    ranked = sorted(
        real_events,
        key=lambda event: abs(float(event.get("event_score", 0))) * float(event.get("materiality_weight", 1)),
        reverse=True,
    )
    important = [event for event in ranked if abs(float(event.get("event_score", 0))) >= 5][:2]
    if not important:
        return "Öne Çıkan Haber Etkisi: Son haftadaki haberlerin ölçülen etkisi sınırlı olduğundan skora ek bir yön sinyali vermedi."
    parts = []
    for event in important:
        score = float(event.get("event_score", 0))
        effect = "olumlu beklentiyi destekleyebilir" if score > 0 else "kısa vadede satış baskısı yaratabilir"
        summary = event.get("summary") or event.get("title", "")
        parts.append(f"{summary} (etki: {score:+.0f}/10; {effect})")
    return "Öne Çıkan Haber Etkisi: " + " ".join(parts)


def _build_anthropic_client(api_key: str) -> ClaudeClientProtocol:
    import anthropic

    sdk_client = anthropic.Anthropic(api_key=api_key)
    return _AnthropicAdapter(sdk_client)


class _AnthropicAdapter:
    def __init__(self, client: Any) -> None:
        self._client = client

    def create_message(self, **kwargs: Any) -> Any:
        return self._client.messages.create(**kwargs)


def _extract_text(response: Any) -> str:
    if hasattr(response, "content") and response.content:
        block = response.content[0]
        if hasattr(block, "text"):
            return block.text
    raise ValueError("Claude yanıtından metin çıkarılamadı.")


def _ensure_valid_json(raw: str) -> None:
    json.loads(raw)


def _local_qualitative_compile(
    input_data: InputSchema,
    math_result: Any,
    kap_metni: Optional[str],
) -> HisseEtkiSkoruOutput:
    """API anahtarı yokken deterministik niteliksel derleme (test/fallback)."""
    quarters = input_data.quarterly_financials
    red_flags: list[str] = []
    notes: list[str] = []
    adjustment = 0.0
    override = False
    override_reason: Optional[str] = None

    latest = quarters[0]
    model_type = get_sector_model_type(input_data.meta.sector_code)
    all_flags = []
    for q in quarters:
        all_flags.extend(q.edge_case_flags)

    if model_type == "real_economy" and "negative_or_zero_ebitda" in all_flags:
        red_flags.append("Negatif veya sıfır FAVÖK tespit edildi.")
        adjustment -= 5.0

    if "negative_or_zero_equity" in all_flags:
        red_flags.append("Negatif veya sıfır özkaynak tespit edildi.")
        adjustment -= 8.0
        override = True
        override_reason = "Özkaynak edge-case — güvenilirlik düşük."

    nd_ebitda = latest.ratios.net_debt_to_ebitda
    if model_type == "real_economy" and nd_ebitda is not None and nd_ebitda > 5:
        red_flags.append(f"Net Borç/FAVÖK yüksek: {nd_ebitda:.2f}")
        adjustment -= 5.0

    cqm = math_result.cash_quality_multiplier
    if cqm is not None and cqm < 0.5:
        red_flags.append(f"Düşük nakit kalitesi (CQM={cqm:.2f})")
        adjustment -= 3.0

    if len(quarters) >= 2:
        rev_now = quarters[0].income_statement.revenue
        rev_prev = quarters[1].income_statement.revenue
        if rev_now is not None and rev_prev is not None and rev_now < rev_prev:
            notes.append("Son çeyrekte gelir düşüşü gözlendi.")

    if kap_metni:
        kap_ozet = kap_metni[:300] + ("..." if len(kap_metni) > 300 else "")
        duygu = _simple_sentiment(kap_metni)
    else:
        kap_ozet = "KAP metni sağlanmadı."
        duygu = "notr"

    if red_flags:
        duygu = "negatif"

    final_score = max(0.0, min(100.0, math_result.matematiksel_baz_skor + adjustment))

    kategori_ozet = {
        cat.kategori: cat.kategori_skoru for cat in math_result.kategori_skorlari
    }

    confidence = _confidence_level(quarters, all_flags, kap_metni)
    oneri = _score_to_recommendation(final_score)

    result = HisseEtkiSkoruOutput(
        symbol=input_data.meta.symbol,
        company_name=input_data.meta.company_name,
        hisse_etki_skoru=round(final_score, 2),
        skor_araligi="0-100",
        guven_seviyesi=confidence,
        math_precompute=math_result,
        qualitative_analysis=QualitativeAnalysis(
            duygu_tonu=duygu,
            kap_ozet=kap_ozet,
            niteliksel_notlar=notes,
            red_flags=red_flags,
            override_uygulandi=override,
            override_nedeni=override_reason,
            niteliksel_duzeltme=adjustment,
        ),
        kategori_ozet=kategori_ozet,
        oneri=oneri,
        analiz_ozeti=(
            f"{input_data.meta.company_name or input_data.meta.symbol} için "
            f"matematiksel baz skor {math_result.matematiksel_baz_skor:.1f}; "
            f"niteliksel düzeltme sonrası {final_score:.1f} puan."
        ),
        generated_at=datetime.now(timezone.utc),
    )
    return _apply_domain_rules_and_reasoning(result, input_data, kap_metni)


def _apply_domain_rules_and_reasoning(
    result: HisseEtkiSkoruOutput,
    input_data: InputSchema,
    kap_metni: Optional[str],
) -> HisseEtkiSkoruOutput:
    """Finansal kuruluş override'larını ve arayüzde gösterilecek gerekçeyi üretir."""
    model_type = get_sector_model_type(input_data.meta.sector_code)
    # API/önbellek üzerinden gelen eski Pydantic çıktılarında alan mevcut
    # olmayabilir. Çıktıyı güncel şemadan yeniden doğrulamak, niteliği her
    # zaman gerçek bir Pydantic alanı haline getirir.
    result = _bind_model_type(result, model_type)
    red_flags = list(result.qualitative_analysis.red_flags)
    score = result.hisse_etki_skoru
    override_reason = result.qualitative_analysis.override_nedeni
    override = result.qualitative_analysis.override_uygulandi

    if model_type == "financial_institution":
        latest_ratios = input_data.quarterly_financials[0].ratios
        car = latest_ratios.capital_adequacy_ratio
        npl = latest_ratios.non_performing_loan_ratio
        # Referans motordaki -70/-40 kompozit tavanları, bu projenin 0-100
        # ölçeğinde sırasıyla 15/30 puana karşılık gelir.
        if car is not None and car < MIN_REGULATORY_CAR_DEFAULT:
            score = min(score, 15.0)
            red_flags.append(
                f"Sermaye Yeterlilik Oranı %{car:.2f}; referans asgari seviye %{MIN_REGULATORY_CAR_DEFAULT:.2f} altında."
            )
            override, override_reason = True, "Sermaye yeterliliği eşiği nedeniyle skor tavanı uygulandı."
        if npl is not None and npl > NPL_WARNING_THRESHOLD_DEFAULT:
            score = min(score, 30.0)
            red_flags.append(
                f"Takipteki Krediler Oranı %{npl:.2f}; uyarı eşiği %{NPL_WARNING_THRESHOLD_DEFAULT:.2f} üzerinde."
            )
            override, override_reason = True, "Aktif kalitesi/TGA eşiği nedeniyle skor tavanı uygulandı."

    qualitative = result.qualitative_analysis.model_copy(
        update={
            "red_flags": list(dict.fromkeys(red_flags)),
            "override_uygulandi": override,
            "override_nedeni": override_reason,
        }
    )
    category_key, category_score = _dominant_category(result.kategori_ozet)
    category_label = labels.label_for(category_key, model_type) if category_key else None
    if qualitative.red_flags:
        reasoning = f"{qualitative.red_flags[0]} Bu risk nihai değerlendirmeyi sınırlandırdı."
    elif category_label:
        direction = "en güçlü olumlu katkıyı sağlıyor" if category_score >= 50 else "sonucu en fazla aşağı çekiyor"
        reasoning = f"{category_label} ({category_score:.0f}/100) {direction}."
    else:
        reasoning = "Yetersiz kategori verisi nedeniyle belirgin bir skor sürükleyicisi tespit edilemedi."
    if kap_metni:
        summary = kap_metni.strip().replace("\n", " ")[:160]
        if summary:
            reasoning += f" Son dönemde öne çıkan gelişme: {summary}"

    return result.model_copy(update={
        "hisse_etki_skoru": round(score, 2),
        "oneri": _score_to_recommendation(score),
        "qualitative_analysis": qualitative,
        "model_type": model_type,
        "karar_gerekcesi": reasoning,
        "analiz_ozeti": reasoning,
    })


def _bind_model_type(result: HisseEtkiSkoruOutput, model_type: str) -> HisseEtkiSkoruOutput:
    """Pydantic çıktısını güncel şemaya bağlar ve model_type alanını garanti eder."""
    payload = result.model_dump(mode="python")
    payload["model_type"] = model_type
    return HisseEtkiSkoruOutput.model_validate(payload)


def _dominant_category(categories: dict[str, float]) -> tuple[Optional[str], Optional[float]]:
    if not categories:
        return None, None
    key = max(categories, key=lambda item: abs(categories[item] - 50.0))
    return key, categories[key]


def _simple_sentiment(text: str) -> str:
    lower = text.lower()
    pos = sum(1 for w in ("artış", "büyüme", "kâr", "pozitif", "rekor") if w in lower)
    neg = sum(1 for w in ("düşüş", "zarar", "negatif", "risk", "dava") if w in lower)
    if pos > neg:
        return "pozitif"
    if neg > pos:
        return "negatif"
    return "notr"


def _confidence_level(
    quarters: list, edge_flags: list[str], kap_metni: Optional[str]
) -> str:
    if len(quarters) >= 4 and not edge_flags and kap_metni:
        return "yuksek"
    if len(quarters) >= 3 and len(edge_flags) <= 1:
        return "orta"
    return "dusuk"


def _score_to_recommendation(score: float) -> str:
    if score >= 75:
        return "guclu_al"
    if score >= 60:
        return "al"
    if score >= 40:
        return "notr"
    if score >= 25:
        return "sat"
    return "guclu_sat"


def run_analysis(company_payload: dict) -> dict[str, Any]:
    """Canlı ``company_payload`` analizinin uygulamalar için açık giriş noktası.

    Bu wrapper dosyanın sonunda tutularak, Streamlit'in içe aktardığı API'nin
    analiz mantığının yüklenmesinden sonra kesin biçimde tanımlanması sağlanır.
    """
    return _run_live_analysis(company_payload)
