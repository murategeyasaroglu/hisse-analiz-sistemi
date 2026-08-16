"""Ham fetch sonucunu PRD INPUT_SCHEMA formatına parse eder."""

from __future__ import annotations

from datetime import datetime, timezone

from fetchers.yahoo_finance import RawFetchResult, RawQuarterData
from parsers.ratio_calculator import compute_ratios
from math_engine import get_sector_model_type
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


def parse_to_input_schema(raw: RawFetchResult) -> InputSchema:
    """RawFetchResult -> doğrulanmış InputSchema."""
    _validate_timestamps(raw)

    sector_code = _derive_sector_code(raw.sector, raw.industry)
    model_type = get_sector_model_type(sector_code)
    quarterly = [_parse_quarter(q, model_type=model_type) for q in raw.quarters]

    return InputSchema(
        meta=CompanyMeta(
            symbol=raw.symbol,
            company_name=raw.company_name,
            sector_code=sector_code,
            sector_name=raw.sector,
            industry=raw.industry,
            currency=raw.currency,
            exchange=raw.exchange,
        ),
        market_data=MarketData(
            market_cap=raw.market_cap,
            current_price=raw.current_price,
            shares_outstanding=raw.shares_outstanding,
            data_timestamp=raw.market_data_timestamp,
            availability_timestamp=raw.market_availability_timestamp,
        ),
        quarterly_financials=quarterly,
        pipeline_fetched_at=datetime.now(timezone.utc),
    )


def _validate_timestamps(raw: RawFetchResult) -> None:
    if raw.market_availability_timestamp is None:
        raise ValueError(
            "Piyasa verisi availability_timestamp olmadan pipeline'a alınamaz."
        )
    for quarter in raw.quarters:
        if quarter.availability_timestamp is None:
            raise ValueError(
                f"{quarter.period_end} dönemi availability_timestamp olmadan "
                "pipeline'a alınamaz."
            )


def _parse_quarter(
    raw_q: RawQuarterData, model_type: str = "real_economy"
) -> QuarterlyFinancials:
    bs_raw = raw_q.balance_sheet
    inc_raw = raw_q.income_statement
    cf_raw = raw_q.cash_flow

    net_debt = _compute_net_debt(
        bs_raw.get("total_debt"), bs_raw.get("cash_and_equivalents")
    )

    balance_sheet = BalanceSheet(
        total_assets=bs_raw.get("total_assets"),
        total_liabilities=bs_raw.get("total_liabilities"),
        shareholders_equity=bs_raw.get("shareholders_equity"),
        total_debt=bs_raw.get("total_debt"),
        cash_and_equivalents=bs_raw.get("cash_and_equivalents"),
        net_debt=net_debt,
    )

    income_statement = IncomeStatement(
        revenue=inc_raw.get("revenue"),
        gross_profit=inc_raw.get("gross_profit"),
        operating_income=inc_raw.get("operating_income"),
        ebitda=inc_raw.get("ebitda"),
        net_income=inc_raw.get("net_income"),
    )

    ocf = cf_raw.get("operating_cash_flow")
    capex = cf_raw.get("capital_expenditure")
    fcf = cf_raw.get("free_cash_flow")
    if fcf is None and ocf is not None and capex is not None:
        fcf = ocf + capex  # yfinance capex genelde negatif

    cash_flow = CashFlowStatement(
        operating_cash_flow=ocf,
        capital_expenditure=capex,
        free_cash_flow=fcf,
    )

    ratios, flags = compute_ratios(
        balance_sheet, income_statement, model_type=model_type
    )

    fiscal_year, fiscal_quarter = _period_parts(raw_q.period_end)

    return QuarterlyFinancials(
        period_label=f"{fiscal_year}-Q{fiscal_quarter}",
        fiscal_year=fiscal_year,
        fiscal_quarter=fiscal_quarter,
        data_timestamp=raw_q.period_end,
        availability_timestamp=raw_q.availability_timestamp,
        balance_sheet=balance_sheet,
        income_statement=income_statement,
        cash_flow=cash_flow,
        ratios=ratios,
        edge_case_flags=flags,
    )


def _compute_net_debt(
    total_debt: float | None, cash: float | None
) -> float | None:
    if total_debt is None:
        return None
    cash_val = cash or 0.0
    return total_debt - cash_val


def _period_parts(period_end: datetime) -> tuple[int, int]:
    month = period_end.month
    quarter = (month - 1) // 3 + 1
    return period_end.year, quarter


def _derive_sector_code(sector: str | None, industry: str | None) -> str | None:
    if not sector:
        return None
    code = sector.upper().replace(" ", "_")[:16]
    if industry:
        suffix = industry.upper().replace(" ", "_")[:8]
        return f"{code}_{suffix}"
    return code
