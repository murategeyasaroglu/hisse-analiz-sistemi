"""Bilanço ve gelir tablosu rasyo hesaplamaları — edge-case korumalı."""

from __future__ import annotations

from schemas import BalanceSheet, IncomeStatement, Ratios

FLAG_NEGATIVE_EQUITY = "negative_or_zero_equity"
FLAG_NEGATIVE_EBITDA = "negative_or_zero_ebitda"
FLAG_ROE_SKIPPED = "roe_skipped_due_to_edge_case"
FLAG_NET_DEBT_EBITDA_SKIPPED = "net_debt_to_ebitda_skipped_due_to_edge_case"
FLAG_DEBT_TO_EQUITY_SKIPPED = "debt_to_equity_skipped_due_to_edge_case"


def compute_ratios(
    balance_sheet: BalanceSheet,
    income_statement: IncomeStatement,
    model_type: str = "real_economy",
) -> tuple[Ratios, list[str]]:
    flags: list[str] = []

    equity = balance_sheet.shareholders_equity
    ebitda = income_statement.ebitda
    net_income = income_statement.net_income
    net_debt = balance_sheet.net_debt

    # Banka/sigorta/yatırım kuruluşlarında Net Borç/FAVÖK ve borç/özsermaye
    # reel sektör rasyolarıdır. Eksik olmaları hata veya edge-case değildir.
    if model_type == "financial_institution":
        return Ratios(roe=_safe_divide(net_income, equity)), flags

    if equity is not None and equity <= 0:
        flags.append(FLAG_NEGATIVE_EQUITY)

    if ebitda is not None and ebitda <= 0:
        flags.append(FLAG_NEGATIVE_EBITDA)

    roe = _safe_divide(net_income, equity)
    if roe is None and net_income is not None and equity is not None:
        flags.append(FLAG_ROE_SKIPPED)

    net_debt_to_ebitda = _safe_divide(net_debt, ebitda)
    if net_debt_to_ebitda is None and net_debt is not None and ebitda is not None:
        flags.append(FLAG_NET_DEBT_EBITDA_SKIPPED)

    current_ratio = None
    if (
        balance_sheet.total_assets is not None
        and balance_sheet.total_liabilities is not None
        and balance_sheet.total_liabilities > 0
    ):
        current_ratio = balance_sheet.total_assets / balance_sheet.total_liabilities

    debt_to_equity = _safe_divide(balance_sheet.total_debt, equity)
    if (
        debt_to_equity is None
        and balance_sheet.total_debt is not None
        and equity is not None
    ):
        flags.append(FLAG_DEBT_TO_EQUITY_SKIPPED)

    return Ratios(
        roe=roe,
        net_debt_to_ebitda=net_debt_to_ebitda,
        current_ratio=current_ratio,
        debt_to_equity=debt_to_equity,
    ), _dedupe_flags(flags)


def _safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None:
        return None
    if denominator <= 0:
        return None
    return numerator / denominator


def _dedupe_flags(flags: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for flag in flags:
        if flag not in seen:
            seen.add(flag)
            result.append(flag)
    return result
