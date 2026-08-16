"""Veri toplama boru hattı — fetch + parse orchestrator."""

from __future__ import annotations

from typing import Any, Optional

import yfinance as yf

from fetchers.yahoo_finance import YahooFinanceFetcher
from math_engine import get_sector_model_type
from parsers.financial_parser import parse_to_input_schema
from schemas import InputSchema


class DataFetcher:
    """Belirtilen hisse sembolü için finansal veri çeker ve INPUT_SCHEMA üretir."""

    def __init__(self, filing_lag_days: int = 45) -> None:
        self._fetcher = YahooFinanceFetcher(filing_lag_days=filing_lag_days)

    def fetch(self, symbol: str, quarter_count: int = 4) -> InputSchema:
        """
        BIST (.IS) veya global sembol için son N çeyrek finansal veriyi çeker.

        Args:
            symbol: Örn. "THYAO.IS", "AAPL"
            quarter_count: Çekilecek çeyrek sayısı (varsayılan 4, max 4)

        Returns:
            Doğrulanmış InputSchema instance

        Raises:
            ValueError: Eksik availability_timestamp veya veri kaynağı hatası
        """
        quarter_count = min(max(quarter_count, 1), 4)
        raw = self._fetcher.fetch(symbol, quarter_count=quarter_count)
        return parse_to_input_schema(raw)


def fetch_company_data(symbol: str, quarter_count: int = 4) -> InputSchema:
    """Kısa yol fonksiyonu."""
    return DataFetcher().fetch(symbol, quarter_count=quarter_count)


def fetch_live_company_payload(symbol: str) -> dict[str, Any]:
    """Yahoo Finance verisini ``analyzer.run_analysis`` girişine dönüştürür.

    Yahoo her piyasa için aynı oran setini sunmadığından, bulunmayan kalemler
    ``None`` bırakılır; bu durum analiz akışını kesmez.
    """
    ticker = yf.Ticker(symbol)
    info = ticker.info or {}
    sector = info.get("sector") or ""
    industry = info.get("industry") or ""
    sector_code = f"{sector}_{industry}".upper().replace(" ", "_")

    financials = {
        "f_k": _number(info.get("trailingPE") or info.get("forwardPE")),
        "pd_dd": _number(info.get("priceToBook")),
        "roe": _percent(info.get("returnOnEquity")),
        "favok_marji": _percent(info.get("ebitdaMargins")),
        "gelir_buyume_yoy": _percent(info.get("revenueGrowth")),
        "gelir_buyume_qoq": _percent(info.get("earningsQuarterlyGrowth")),
        "net_borc_favok": _number(info.get("netDebtToEbitda")),
        "faaliyet_nakit_akisi": _number(info.get("operatingCashflow")),
        "net_kar": _number(info.get("netIncomeToCommon")),
        "ozkaynak": _number(info.get("totalStockholderEquity")),
        "net_faiz_marji": _percent(info.get("netInterestMargin")),
        "sermaye_yeterlilik_orani": _percent(info.get("capitalAdequacyRatio")),
        "takipteki_krediler_orani": _percent(info.get("nonPerformingLoanRatio")),
    }
    return {
        "company_identifier": {
            "ticker": symbol.upper(),
            "company_name": info.get("longName") or info.get("shortName"),
            "sector_code": sector_code,
            "sector_name": sector,
            "industry": industry,
            "model_type": get_sector_model_type(sector_code),
        },
        "financials": financials,
        "peer_benchmark_data": {},
        "qualitative_events": [],
        "market_data": {
            "current_price": _number(info.get("currentPrice") or info.get("regularMarketPrice")),
            "daily_change_percent": _number(info.get("regularMarketChangePercent")),
            "market_cap": _number(info.get("marketCap")),
            "currency": info.get("currency"),
        },
    }


def fetch_price_history(symbol: str, range_code: str = "1A"):
    """Seçilen terminal aralığı için kapanış fiyat serisini getirir."""
    period_map = {
        "1G": ("1d", "5m"),
        "5G": ("5d", "30m"),
        "1A": ("1mo", "1h"),
        "6A": ("6mo", "1d"),
        "YBK": ("ytd", "1d"),
        "1Y": ("1y", "1d"),
        "5Y": ("5y", "1wk"),
        "Maks.": ("max", "1mo"),
    }
    period, interval = period_map.get(range_code, period_map["1A"])
    if range_code != "1G":
        return yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=True)

    # Önceki seans kapanışını bulmak için iki günlük gün içi seri alınır;
    # çizimde yalnızca son seans tutulur.
    history = yf.Ticker(symbol).history(period="2d", interval=interval, auto_adjust=True)
    if history.empty:
        return history
    last_session = max(history.index.date)
    previous = history[history.index.date < last_session]
    current = history[history.index.date == last_session].copy()
    if not previous.empty:
        current.attrs["reference_close"] = float(previous["Close"].dropna().iloc[-1])
    return current


def _number(value: Any) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _percent(value: Any) -> Optional[float]:
    number = _number(value)
    if number is None:
        return None
    return number * 100 if -1.0 <= number <= 1.0 else number
