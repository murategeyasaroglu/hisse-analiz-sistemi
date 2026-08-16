"""Deterministik matematik motoru — Z-skor, CQM, kategori ağırlıkları."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import mean, pstdev
from typing import Optional

from analysis_schemas import CategoryScore, MathPrecompute
from schemas import InputSchema, QuarterlyFinancials

Z_SCORE_MIN = -10.0
Z_SCORE_MAX = 10.0

# Yahoo/iş ortaklarından gelen sektör kodları bu sabit isimlerle birebir
# eşleşmeyebilir; anahtar sözcük eşlemesi GARAN.IS ve TERA.IS gibi BIST
# finansallarını da doğru modele yönlendirir.
FINANCIAL_INSTITUTION_SECTOR_CODES = frozenset({"BANK", "INSUR", "INVEST_CO", "LEASING"})
FINANCIAL_SECTOR_TOKENS = frozenset({"BANK", "BANKS", "BANKING", "INSUR", "INSURANCE", "SIGORTA", "INVEST", "INVESTMENT", "FINANCIAL", "FINANCE", "LEASING", "BROKER"})
MIN_REGULATORY_CAR_DEFAULT = 12.0
NPL_WARNING_THRESHOLD_DEFAULT = 5.0


def get_sector_model_type(sector_code: Optional[str]) -> str:
    """Sektör kodundan reel sektör/finansal kuruluş hesaplama modelini seçer."""
    normalized = (sector_code or "").upper().replace("-", "_").replace(" ", "_")
    tokens = set(normalized.split("_"))
    if normalized in FINANCIAL_INSTITUTION_SECTOR_CODES or tokens & FINANCIAL_SECTOR_TOKENS:
        return "financial_institution"
    return "real_economy"

CATEGORY_WEIGHTS: dict[str, float] = {
    "karlilik": 0.25,
    "finansal_saglik": 0.25,
    "borc_yuk": 0.20,
    "nakit_kalitesi": 0.20,
    "buyume": 0.10,
}

FLAG_CQM_NET_INCOME_NON_POSITIVE = "cqm_skipped_net_income_non_positive"
FLAG_CQM_CFO_MISSING = "cqm_skipped_cfo_missing"
FLAG_CQM_NET_INCOME_MISSING = "cqm_skipped_net_income_missing"


@dataclass
class MetricSeries:
    name: str
    values: list[Optional[float]]


def clip_z_score(value: float) -> float:
    return max(Z_SCORE_MIN, min(Z_SCORE_MAX, value))


def compute_z_score(
    values: list[Optional[float]], latest_index: int = 0
) -> Optional[float]:
    """Son dönem değerinin seri içi Z-skorunu hesaplar ve clip(-10, 10) uygular."""
    numeric = [v for v in values if v is not None]
    if len(numeric) < 2:
        return None

    latest = values[latest_index] if latest_index < len(values) else None
    if latest is None:
        return None

    mu = mean(numeric)
    sigma = pstdev(numeric)
    if sigma == 0:
        return 0.0

    return clip_z_score((latest - mu) / sigma)


def compute_cash_quality_multiplier(
    operating_cash_flow: Optional[float],
    net_income: Optional[float],
) -> tuple[Optional[float], list[str]]:
    """
    Cash Quality Multiplier = CFO / Net Kâr.

    Net kâr <= 0 veya eksik veri durumunda null döner.
    """
    flags: list[str] = []

    if operating_cash_flow is None:
        flags.append(FLAG_CQM_CFO_MISSING)
        return None, flags

    if net_income is None:
        flags.append(FLAG_CQM_NET_INCOME_MISSING)
        return None, flags

    if net_income <= 0:
        flags.append(FLAG_CQM_NET_INCOME_NON_POSITIVE)
        return None, flags

    return operating_cash_flow / net_income, flags


def z_to_score(z: Optional[float]) -> float:
    """Z-skoru 0-100 skala puanına dönüştürür (50 = nötr)."""
    if z is None:
        return 50.0
    return max(0.0, min(100.0, 50.0 + z * 5.0))


def _quarter_metrics(quarters: list[QuarterlyFinancials]) -> dict[str, MetricSeries]:
    """Çeyreklik metrik serilerini çıkarır (index 0 = en güncel)."""
    return {
        "roe": MetricSeries(
            "roe", [q.ratios.roe for q in quarters]
        ),
        "net_margin": MetricSeries(
            "net_margin",
            [
                _safe_div(q.income_statement.net_income, q.income_statement.revenue)
                for q in quarters
            ],
        ),
        "current_ratio": MetricSeries(
            "current_ratio", [q.ratios.current_ratio for q in quarters]
        ),
        "debt_to_equity": MetricSeries(
            "debt_to_equity", [q.ratios.debt_to_equity for q in quarters]
        ),
        "net_debt_to_ebitda": MetricSeries(
            "net_debt_to_ebitda", [q.ratios.net_debt_to_ebitda for q in quarters]
        ),
        "revenue_growth": MetricSeries(
            "revenue_growth", _revenue_growth_series(quarters)
        ),
        "free_cash_flow": MetricSeries(
            "free_cash_flow", [q.cash_flow.free_cash_flow for q in quarters]
        ),
    }


def _financial_quarter_metrics(quarters: list[QuarterlyFinancials]) -> dict[str, MetricSeries]:
    """Finansal kurumlara özgü seri. Eksik veri nötr puanlanır, hata üretilmez."""
    return {
        "net_interest_margin": MetricSeries("net_interest_margin", [q.ratios.net_interest_margin for q in quarters]),
        "roe": MetricSeries("roe", [q.ratios.roe for q in quarters]),
        "capital_adequacy": MetricSeries("capital_adequacy", [q.ratios.capital_adequacy_ratio for q in quarters]),
        "asset_quality": MetricSeries("asset_quality", [q.ratios.non_performing_loan_ratio for q in quarters]),
    }


def _revenue_growth_series(
    quarters: list[QuarterlyFinancials],
) -> list[Optional[float]]:
    """YoY benzeri büyüme: önceki çeyreğe göre gelir değişimi."""
    growth: list[Optional[float]] = []
    for i, q in enumerate(quarters):
        rev = q.income_statement.revenue
        if i + 1 >= len(quarters):
            growth.append(None)
            continue
        prev_rev = quarters[i + 1].income_statement.revenue
        if rev is None or prev_rev is None or prev_rev == 0:
            growth.append(None)
        else:
            growth.append((rev - prev_rev) / abs(prev_rev))
    return growth


def _safe_div(num: Optional[float], den: Optional[float]) -> Optional[float]:
    if num is None or den is None or den == 0:
        return None
    return num / den


def _invert_z(z: Optional[float]) -> Optional[float]:
    """Borç yükü gibi düşük=iyi metrikler için Z-skoru ters çevirir."""
    if z is None:
        return None
    return clip_z_score(-z)


@dataclass
class CategoryResult:
    kategori: str
    agirlik: float
    metric_z_scores: dict[str, Optional[float]] = field(default_factory=dict)

    @property
    def avg_z(self) -> Optional[float]:
        valid = [z for z in self.metric_z_scores.values() if z is not None]
        if not valid:
            return None
        return sum(valid) / len(valid)

    @property
    def kategori_skoru(self) -> float:
        return z_to_score(self.avg_z)


def compute_category_scores(
    metrics: dict[str, MetricSeries],
    cqm: Optional[float],
) -> list[CategoryResult]:
    z_roe = compute_z_score(metrics["roe"].values)
    z_margin = compute_z_score(metrics["net_margin"].values)
    z_current = compute_z_score(metrics["current_ratio"].values)
    z_dte = _invert_z(compute_z_score(metrics["debt_to_equity"].values))
    z_nd_ebitda = _invert_z(compute_z_score(metrics["net_debt_to_ebitda"].values))
    z_growth = compute_z_score(metrics["revenue_growth"].values)
    z_fcf = compute_z_score(metrics["free_cash_flow"].values)

    cqm_z: Optional[float] = None
    if cqm is not None:
        cqm_z = clip_z_score((cqm - 1.0) * 2.0)

    return [
        CategoryResult(
            "karlilik",
            CATEGORY_WEIGHTS["karlilik"],
            {"roe": z_roe, "net_margin": z_margin},
        ),
        CategoryResult(
            "finansal_saglik",
            CATEGORY_WEIGHTS["finansal_saglik"],
            {"current_ratio": z_current, "debt_to_equity_inv": z_dte},
        ),
        CategoryResult(
            "borc_yuk",
            CATEGORY_WEIGHTS["borc_yuk"],
            {"net_debt_to_ebitda_inv": z_nd_ebitda},
        ),
        CategoryResult(
            "nakit_kalitesi",
            CATEGORY_WEIGHTS["nakit_kalitesi"],
            {"cash_quality_multiplier": cqm_z, "free_cash_flow": z_fcf},
        ),
        CategoryResult(
            "buyume",
            CATEGORY_WEIGHTS["buyume"],
            {"revenue_growth": z_growth},
        ),
    ]


def weighted_base_score(categories: list[CategoryResult]) -> float:
    total_weight = 0.0
    weighted_sum = 0.0
    for cat in categories:
        weighted_sum += cat.kategori_skoru * cat.agirlik
        total_weight += cat.agirlik
    if total_weight == 0:
        return 50.0
    return weighted_sum / total_weight


def compute_financial_institution_category_scores(
    quarters: list[QuarterlyFinancials],
) -> list[CategoryResult]:
    metrics = _financial_quarter_metrics(quarters)
    # TGA/NPL düşük oldukça olumludur.
    npl_z = _invert_z(compute_z_score(metrics["asset_quality"].values))
    return [
        CategoryResult("net_interest_margin", 0.25, {"net_interest_margin": compute_z_score(metrics["net_interest_margin"].values)}),
        CategoryResult("profitability_roe", 0.25, {"roe": compute_z_score(metrics["roe"].values)}),
        CategoryResult("capital_adequacy", 0.30, {"capital_adequacy_ratio": compute_z_score(metrics["capital_adequacy"].values)}),
        CategoryResult("asset_quality", 0.20, {"non_performing_loan_ratio_inv": npl_z}),
    ]


def compute_math_precompute(input_data: InputSchema) -> MathPrecompute:
    """INPUT_SCHEMA üzerinden deterministik matematiksel ön hesaplama."""
    quarters = input_data.quarterly_financials
    latest = quarters[0]

    model_type = get_sector_model_type(input_data.meta.sector_code)
    if model_type == "financial_institution":
        # Banka sigorta tablolarında CFO/FAVÖK mantığı uygulanmaz.
        cqm, cqm_flags = None, ["cash_quality_not_applicable_financial_institution"]
        categories = compute_financial_institution_category_scores(quarters)
    else:
        metrics = _quarter_metrics(quarters)
        cqm, cqm_flags = compute_cash_quality_multiplier(
            latest.cash_flow.operating_cash_flow, latest.income_statement.net_income,
        )
        categories = compute_category_scores(metrics, cqm)

    all_z: dict[str, Optional[float]] = {}
    for cat in categories:
        for metric_name, z_val in cat.metric_z_scores.items():
            all_z[f"{cat.kategori}.{metric_name}"] = z_val

    category_scores = [
        CategoryScore(
            kategori=cat.kategori,
            agirlik=cat.agirlik,
            ham_z_skor=cat.avg_z,
            kategori_skoru=round(cat.kategori_skoru, 2),
        )
        for cat in categories
    ]

    base = weighted_base_score(categories)

    return MathPrecompute(
        z_skorlar=all_z,
        cash_quality_multiplier=round(cqm, 4) if cqm is not None else None,
        cash_quality_flags=cqm_flags,
        kategori_skorlari=category_scores,
        matematiksel_baz_skor=round(base, 2),
    )


def validate_category_weights() -> bool:
    """Kategori ağırlıklarının 1.0'a toplandığını doğrular."""
    total = sum(CATEGORY_WEIGHTS.values())
    return math.isclose(total, 1.0, rel_tol=1e-9)
