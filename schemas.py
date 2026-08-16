"""Pydantic v2 modelleri — PRD Bölüm 4.1 INPUT_SCHEMA."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TimestampedValue(BaseModel):
    """Zaman damgalı tekil değer (look-ahead bias koruması)."""

    model_config = ConfigDict(extra="forbid")

    value: Optional[float] = None
    data_timestamp: datetime
    availability_timestamp: datetime

    @model_validator(mode="after")
    def availability_required(self) -> TimestampedValue:
        if self.availability_timestamp is None:
            raise ValueError("availability_timestamp zorunludur.")
        return self


class BalanceSheet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_assets: Optional[float] = None
    total_liabilities: Optional[float] = None
    shareholders_equity: Optional[float] = None
    total_debt: Optional[float] = None
    cash_and_equivalents: Optional[float] = None
    net_debt: Optional[float] = None


class IncomeStatement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revenue: Optional[float] = None
    gross_profit: Optional[float] = None
    operating_income: Optional[float] = None
    ebitda: Optional[float] = None
    net_income: Optional[float] = None


class CashFlowStatement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operating_cash_flow: Optional[float] = None
    capital_expenditure: Optional[float] = None
    free_cash_flow: Optional[float] = None


class Ratios(BaseModel):
    model_config = ConfigDict(extra="forbid")

    roe: Optional[float] = Field(default=None, description="Return on Equity")
    net_debt_to_ebitda: Optional[float] = Field(
        default=None, description="Net Borç / FAVÖK"
    )
    current_ratio: Optional[float] = None
    debt_to_equity: Optional[float] = None
    # Finansal kuruluşlara özgü, geriye dönük uyumlu isteğe bağlı metrikler.
    net_interest_margin: Optional[float] = None
    capital_adequacy_ratio: Optional[float] = None
    non_performing_loan_ratio: Optional[float] = None


class QuarterlyFinancials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period_label: str = Field(..., description="Örn. 2024-Q3")
    fiscal_year: int
    fiscal_quarter: int
    data_timestamp: datetime
    availability_timestamp: datetime
    balance_sheet: BalanceSheet
    income_statement: IncomeStatement
    cash_flow: CashFlowStatement
    ratios: Ratios
    edge_case_flags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def availability_required(self) -> QuarterlyFinancials:
        if self.availability_timestamp is None:
            raise ValueError("availability_timestamp zorunludur.")
        return self


class MarketData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market_cap: Optional[float] = None
    current_price: Optional[float] = None
    shares_outstanding: Optional[float] = None
    data_timestamp: datetime
    availability_timestamp: datetime

    @model_validator(mode="after")
    def availability_required(self) -> MarketData:
        if self.availability_timestamp is None:
            raise ValueError("availability_timestamp zorunludur.")
        return self


class CompanyMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    company_name: Optional[str] = None
    sector_code: Optional[str] = None
    sector_name: Optional[str] = None
    industry: Optional[str] = None
    currency: str = "USD"
    exchange: Optional[str] = None


class InputSchema(BaseModel):
    """PRD Bölüm 4.1 — pipeline giriş şeması."""

    model_config = ConfigDict(extra="forbid")

    meta: CompanyMeta
    market_data: MarketData
    quarterly_financials: list[QuarterlyFinancials] = Field(
        ..., min_length=1, max_length=4
    )
    pipeline_fetched_at: datetime

    @field_validator("quarterly_financials")
    @classmethod
    def validate_quarter_count(
        cls, value: list[QuarterlyFinancials]
    ) -> list[QuarterlyFinancials]:
        if not value:
            raise ValueError("En az bir çeyrek finansal veri gerekli.")
        if len(value) > 4:
            raise ValueError("En fazla 4 çeyrek finansal veri desteklenir.")
        return value


# PRD referans alias
INPUT_SCHEMA = InputSchema
