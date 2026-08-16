"""Data pipeline birim testleri."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from fetchers.yahoo_finance import RawFetchResult, _is_financial_institution
from parsers.financial_parser import _validate_timestamps
from parsers.ratio_calculator import compute_ratios
from schemas import BalanceSheet, IncomeStatement


def test_financial_sector_guardrail_blocks_banks():
    assert _is_financial_institution("financial services", "banks - diversified")
    assert _is_financial_institution("", "life insurance")
    assert not _is_financial_institution("technology", "consumer electronics")


def test_roe_null_when_equity_non_positive():
    bs = BalanceSheet(
        total_assets=100.0,
        total_liabilities=60.0,
        shareholders_equity=0.0,
        total_debt=20.0,
        cash_and_equivalents=5.0,
        net_debt=15.0,
    )
    inc = IncomeStatement(
        revenue=50.0,
        gross_profit=20.0,
        operating_income=10.0,
        ebitda=12.0,
        net_income=5.0,
    )
    ratios, flags = compute_ratios(bs, inc)
    assert ratios.roe is None
    assert "negative_or_zero_equity" in flags
    assert "roe_skipped_due_to_edge_case" in flags


def test_net_debt_ebitda_null_when_ebitda_non_positive():
    bs = BalanceSheet(
        total_assets=100.0,
        total_liabilities=40.0,
        shareholders_equity=60.0,
        total_debt=20.0,
        cash_and_equivalents=5.0,
        net_debt=15.0,
    )
    inc = IncomeStatement(
        revenue=50.0,
        gross_profit=20.0,
        operating_income=-2.0,
        ebitda=-1.0,
        net_income=-3.0,
    )
    ratios, flags = compute_ratios(bs, inc)
    assert ratios.net_debt_to_ebitda is None
    assert "negative_or_zero_ebitda" in flags
    assert "net_debt_to_ebitda_skipped_due_to_edge_case" in flags


def test_pipeline_rejects_missing_availability_timestamp():
    now = datetime.now(timezone.utc)
    raw = RawFetchResult(
        symbol="TEST",
        company_name="Test Co",
        sector="Technology",
        industry="Software",
        currency="USD",
        exchange="NMS",
        market_cap=1000.0,
        current_price=10.0,
        shares_outstanding=100.0,
        market_data_timestamp=now,
        market_availability_timestamp=None,  # type: ignore[arg-type]
        quarters=[],
    )
    with pytest.raises(ValueError, match="availability_timestamp"):
        _validate_timestamps(raw)
