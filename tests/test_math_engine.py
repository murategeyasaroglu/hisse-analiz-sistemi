"""Math engine birim testleri."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from math_engine import (
    CATEGORY_WEIGHTS,
    clip_z_score,
    compute_cash_quality_multiplier,
    compute_math_precompute,
    compute_z_score,
    validate_category_weights,
)
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


def _sample_quarter(
    label: str,
    year: int,
    quarter: int,
    equity: float,
    ebitda: float,
    net_income: float,
    revenue: float,
    ocf: float,
) -> QuarterlyFinancials:
    now = datetime.now(timezone.utc)
    return QuarterlyFinancials(
        period_label=label,
        fiscal_year=year,
        fiscal_quarter=quarter,
        data_timestamp=now,
        availability_timestamp=now,
        balance_sheet=BalanceSheet(
            total_assets=1000.0,
            total_liabilities=400.0,
            shareholders_equity=equity,
            total_debt=200.0,
            cash_and_equivalents=50.0,
            net_debt=150.0,
        ),
        income_statement=IncomeStatement(
            revenue=revenue,
            gross_profit=revenue * 0.4,
            operating_income=ebitda * 0.8,
            ebitda=ebitda,
            net_income=net_income,
        ),
        cash_flow=CashFlowStatement(
            operating_cash_flow=ocf,
            capital_expenditure=-10.0,
            free_cash_flow=ocf - 10.0,
        ),
        ratios=Ratios(
            roe=net_income / equity if equity > 0 else None,
            net_debt_to_ebitda=150.0 / ebitda if ebitda > 0 else None,
            current_ratio=2.5,
            debt_to_equity=200.0 / equity if equity > 0 else None,
        ),
        edge_case_flags=[],
    )


def test_clip_z_score_bounds():
    assert clip_z_score(15.0) == 10.0
    assert clip_z_score(-20.0) == -10.0
    assert clip_z_score(3.5) == 3.5


def test_compute_z_score_with_clip():
    values = [10.0, 12.0, 14.0, 100.0]
    z = compute_z_score(values, latest_index=0)
    assert z is not None
    assert z == -10.0


def test_cash_quality_multiplier():
    cqm, flags = compute_cash_quality_multiplier(200.0, 100.0)
    assert cqm == 2.0
    assert flags == []

    cqm_neg, flags_neg = compute_cash_quality_multiplier(100.0, -5.0)
    assert cqm_neg is None
    assert "cqm_skipped_net_income_non_positive" in flags_neg


def test_category_weights_sum_to_one():
    assert validate_category_weights() is True
    assert abs(sum(CATEGORY_WEIGHTS.values()) - 1.0) < 1e-9


def test_compute_math_precompute():
    quarters = [
        _sample_quarter("2025-Q4", 2025, 4, 600.0, 120.0, 80.0, 500.0, 100.0),
        _sample_quarter("2025-Q3", 2025, 3, 580.0, 110.0, 75.0, 480.0, 95.0),
        _sample_quarter("2025-Q2", 2025, 2, 560.0, 100.0, 70.0, 460.0, 90.0),
        _sample_quarter("2025-Q1", 2025, 1, 540.0, 95.0, 65.0, 440.0, 85.0),
    ]
    now = datetime.now(timezone.utc)
    input_data = InputSchema(
        meta=CompanyMeta(symbol="TEST", company_name="Test A.Ş.", currency="TRY"),
        market_data=MarketData(
            market_cap=1e9,
            data_timestamp=now,
            availability_timestamp=now,
        ),
        quarterly_financials=quarters,
        pipeline_fetched_at=now,
    )

    result = compute_math_precompute(input_data)
    assert 0 <= result.matematiksel_baz_skor <= 100
    assert result.cash_quality_multiplier == pytest.approx(1.25, rel=1e-3)
    assert len(result.kategori_skorlari) == 5
