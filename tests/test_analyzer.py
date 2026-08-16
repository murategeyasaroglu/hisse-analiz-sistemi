"""Analyzer birim ve mock entegrasyon testleri."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from analyzer import Analyzer, JSON_PREFILL, analyze_company
from analysis_schemas import HisseEtkiSkoruOutput
from math_engine import compute_math_precompute
from schemas import (
    BalanceSheet,
    CashFlowStatement,
    CompanyMeta,
    IncomeStatement,
    InputSchema,
    MarketData,
    QuarterlyFinancials,
    Ratios,
)


@dataclass
class FakeTextBlock:
    text: str


@dataclass
class FakeResponse:
    content: list[FakeTextBlock]


class FakeClaudeClient:
    def __init__(self, json_body: str) -> None:
        self.json_body = json_body
        self.last_kwargs: dict | None = None

    def create_message(self, **kwargs):
        self.last_kwargs = kwargs
        return FakeResponse(content=[FakeTextBlock(text=json_body_without_brace(self.json_body))])


def json_body_without_brace(full_json: str) -> str:
    assert full_json.startswith("{")
    return full_json[1:]


def _minimal_input() -> InputSchema:
    now = datetime.now(timezone.utc)
    q = QuarterlyFinancials(
        period_label="2025-Q4",
        fiscal_year=2025,
        fiscal_quarter=4,
        data_timestamp=now,
        availability_timestamp=now,
        balance_sheet=BalanceSheet(
            total_assets=1000.0,
            total_liabilities=400.0,
            shareholders_equity=600.0,
            total_debt=200.0,
            cash_and_equivalents=50.0,
            net_debt=150.0,
        ),
        income_statement=IncomeStatement(
            revenue=500.0,
            gross_profit=200.0,
            operating_income=100.0,
            ebitda=120.0,
            net_income=80.0,
        ),
        cash_flow=CashFlowStatement(
            operating_cash_flow=100.0,
            capital_expenditure=-10.0,
            free_cash_flow=90.0,
        ),
        ratios=Ratios(
            roe=0.13,
            net_debt_to_ebitda=1.25,
            current_ratio=2.5,
            debt_to_equity=0.33,
        ),
        edge_case_flags=[],
    )
    return InputSchema(
        meta=CompanyMeta(symbol="TEST", company_name="Test A.Ş."),
        market_data=MarketData(
            market_cap=1e9,
            data_timestamp=now,
            availability_timestamp=now,
        ),
        quarterly_financials=[q],
        pipeline_fetched_at=now,
    )


def test_local_fallback_produces_valid_output():
    result = analyze_company(_minimal_input(), use_local_fallback=True)
    assert isinstance(result, HisseEtkiSkoruOutput)
    assert 0 <= result.hisse_etki_skoru <= 100
    assert result.symbol == "TEST"


def test_claude_prefill_and_temperature():
    input_data = _minimal_input()
    math_result = compute_math_precompute(input_data)
    kategori_ozet = {
        c.kategori: c.kategori_skoru for c in math_result.kategori_skorlari
    }
    fake_output = {
        "symbol": "TEST",
        "company_name": "Test A.Ş.",
        "hisse_etki_skoru": 65.0,
        "skor_araligi": "0-100",
        "guven_seviyesi": "orta",
        "math_precompute": math_result.model_dump(mode="json"),
        "qualitative_analysis": {
            "duygu_tonu": "notr",
            "kap_ozet": "KAP metni sağlanmadı.",
            "niteliksel_notlar": [],
            "red_flags": [],
            "override_uygulandi": False,
            "override_nedeni": None,
            "niteliksel_duzeltme": 0.0,
        },
        "kategori_ozet": kategori_ozet,
        "oneri": "notr",
        "analiz_ozeti": "Test analizi.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    import json

    full_json = json.dumps(fake_output, ensure_ascii=False)
    client = FakeClaudeClient(full_json)
    analyzer = Analyzer(client=client, use_local_fallback=False)
    result = analyzer.analyze(input_data)

    assert client.last_kwargs is not None
    assert client.last_kwargs["temperature"] == 0
    messages = client.last_kwargs["messages"]
    assert messages[-1]["role"] == "assistant"
    assert messages[-1]["content"] == JSON_PREFILL
    assert result.hisse_etki_skoru == 65.0


def test_json_prefill_merge():
    continuation = '"symbol": "TEST", "hisse_etki_skoru": 50.0}'
    merged = JSON_PREFILL + continuation
    import json

    parsed = json.loads(merged)
    assert parsed["symbol"] == "TEST"
