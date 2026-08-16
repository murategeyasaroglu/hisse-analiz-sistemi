"""Yahoo Finance (yfinance) üzerinden ham finansal veri çekici."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pandas as pd
import yfinance as yf


FINANCIAL_SECTOR_KEYWORDS = frozenset(
    {
        "bank",
        "banking",
        "banks",
        "insurance",
        "financial services",
        "financial",
        "credit",
        "capital markets",
        "mortgage",
        "reit",
        "asset management",
        "sigorta",
        "banka",
        "finans",
        "finansal",
    }
)

FINANCIAL_INDUSTRY_KEYWORDS = frozenset(
    {
        "bank",
        "banks",
        "insurance",
        "credit",
        "mortgage",
        "reit",
        "asset management",
        "capital markets",
        "financial conglomerates",
        "diversified financial",
        "sigorta",
        "banka",
    }
)

# Tipik finansal tablo yayın gecikmesi (KAP/SEC filing simülasyonu)
DEFAULT_FILING_LAG_DAYS = 45


@dataclass
class RawQuarterData:
    period_end: datetime
    availability_timestamp: datetime
    balance_sheet: dict[str, Optional[float]]
    income_statement: dict[str, Optional[float]]
    cash_flow: dict[str, Optional[float]]


@dataclass
class RawFetchResult:
    symbol: str
    company_name: Optional[str]
    sector: Optional[str]
    industry: Optional[str]
    currency: str
    exchange: Optional[str]
    market_cap: Optional[float]
    current_price: Optional[float]
    shares_outstanding: Optional[float]
    market_data_timestamp: datetime
    market_availability_timestamp: datetime
    quarters: list[RawQuarterData] = field(default_factory=list)


class YahooFinanceFetcher:
    """yfinance ile BIST (.IS) ve global hisse verisi çeker."""

    def __init__(self, filing_lag_days: int = DEFAULT_FILING_LAG_DAYS) -> None:
        self.filing_lag_days = filing_lag_days

    def fetch(self, symbol: str, quarter_count: int = 4) -> RawFetchResult:
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}

        now = datetime.now(timezone.utc)
        market_cap = _safe_float(info.get("marketCap"))
        current_price = _safe_float(
            info.get("currentPrice") or info.get("regularMarketPrice")
        )
        shares = _safe_float(info.get("sharesOutstanding"))

        quarters = self._fetch_quarterly_data(ticker, quarter_count)

        return RawFetchResult(
            symbol=symbol.upper(),
            company_name=info.get("longName") or info.get("shortName"),
            sector=info.get("sector"),
            industry=info.get("industry"),
            currency=info.get("currency") or "USD",
            exchange=info.get("exchange"),
            market_cap=market_cap,
            current_price=current_price,
            shares_outstanding=shares,
            market_data_timestamp=now,
            market_availability_timestamp=now,
            quarters=quarters,
        )

    def _fetch_quarterly_data(
        self, ticker: yf.Ticker, quarter_count: int
    ) -> list[RawQuarterData]:
        balance_df = ticker.quarterly_balance_sheet
        income_df = ticker.quarterly_income_stmt
        cashflow_df = ticker.quarterly_cashflow

        if balance_df is None or balance_df.empty:
            raise ValueError(f"Bilanço verisi bulunamadı: {ticker.ticker}")

        periods = list(balance_df.columns[:quarter_count])
        quarters: list[RawQuarterData] = []

        for period in periods:
            period_end = _to_utc_datetime(period)
            availability = period_end + timedelta(days=self.filing_lag_days)

            bs = _extract_row_values(balance_df, period, _BALANCE_SHEET_MAP)
            inc = _extract_row_values(
                income_df, period, _INCOME_STATEMENT_MAP
            ) if income_df is not None and not income_df.empty else {}
            cf = _extract_row_values(
                cashflow_df, period, _CASH_FLOW_MAP
            ) if cashflow_df is not None and not cashflow_df.empty else {}

            quarters.append(
                RawQuarterData(
                    period_end=period_end,
                    availability_timestamp=availability,
                    balance_sheet=bs,
                    income_statement=inc,
                    cash_flow=cf,
                )
            )

        return quarters


def _is_financial_institution(sector: str, industry: str) -> bool:
    for keyword in FINANCIAL_SECTOR_KEYWORDS:
        if keyword in sector:
            return True
    for keyword in FINANCIAL_INDUSTRY_KEYWORDS:
        if keyword in industry:
            return True
    return False


def _to_utc_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, pd.Timestamp):
        dt = value.to_pydatetime()
    else:
        dt = pd.Timestamp(value).to_pydatetime()

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        result = float(value)
        if pd.isna(result):
            return None
        return result
    except (TypeError, ValueError):
        return None


def _extract_row_values(
    df: pd.DataFrame,
    period: Any,
    field_map: dict[str, list[str]],
) -> dict[str, Optional[float]]:
    result: dict[str, Optional[float]] = {}
    for target_field, candidate_rows in field_map.items():
        value = None
        for row_name in candidate_rows:
            if row_name in df.index:
                raw = df.loc[row_name, period]
                value = _safe_float(raw)
                if value is not None:
                    break
        result[target_field] = value
    return result


_BALANCE_SHEET_MAP: dict[str, list[str]] = {
    "total_assets": ["Total Assets"],
    "total_liabilities": ["Total Liabilities Net Minority Interest", "Total Liabilities"],
    "shareholders_equity": [
        "Stockholders Equity",
        "Total Equity Gross Minority Interest",
        "Common Stock Equity",
    ],
    "total_debt": ["Total Debt", "Long Term Debt And Capital Lease Obligation"],
    "cash_and_equivalents": [
        "Cash And Cash Equivalents",
        "Cash Cash Equivalents And Short Term Investments",
    ],
}

_INCOME_STATEMENT_MAP: dict[str, list[str]] = {
    "revenue": ["Total Revenue", "Operating Revenue"],
    "gross_profit": ["Gross Profit"],
    "operating_income": ["Operating Income", "EBIT"],
    "ebitda": ["EBITDA", "Normalized EBITDA"],
    "net_income": ["Net Income", "Net Income Common Stockholders"],
}

_CASH_FLOW_MAP: dict[str, list[str]] = {
    "operating_cash_flow": [
        "Operating Cash Flow",
        "Cash Flow From Continuing Operating Activities",
    ],
    "capital_expenditure": ["Capital Expenditure", "Purchase Of PPE"],
    "free_cash_flow": ["Free Cash Flow"],
}
