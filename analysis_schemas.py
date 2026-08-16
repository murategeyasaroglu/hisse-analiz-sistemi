"""Analiz motoru çıktı şemaları — Hisse Etki Skoru JSON."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class CategoryScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kategori: str
    agirlik: float
    ham_z_skor: Optional[float] = None
    kategori_skoru: float = Field(..., ge=0, le=100)


class MathPrecompute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    z_skorlar: dict[str, Optional[float]]
    cash_quality_multiplier: Optional[float]
    cash_quality_flags: list[str] = Field(default_factory=list)
    kategori_skorlari: list[CategoryScore]
    matematiksel_baz_skor: float = Field(..., ge=0, le=100)


class QualitativeAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    duygu_tonu: Literal["pozitif", "notr", "negatif"]
    kap_ozet: str
    niteliksel_notlar: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    override_uygulandi: bool = False
    override_nedeni: Optional[str] = None
    niteliksel_duzeltme: float = Field(default=0.0, ge=-15, le=15)


class HisseEtkiSkoruOutput(BaseModel):
    """Nihai analiz motoru JSON çıktısı."""

    model_config = ConfigDict(extra="forbid")

    symbol: str
    company_name: Optional[str] = None
    hisse_etki_skoru: float = Field(..., ge=0, le=100)
    skor_araligi: str = "0-100"
    guven_seviyesi: Literal["dusuk", "orta", "yuksek"]
    math_precompute: MathPrecompute
    qualitative_analysis: QualitativeAnalysis
    kategori_ozet: dict[str, float]
    oneri: Literal["guclu_al", "al", "notr", "sat", "guclu_sat"]
    analiz_ozeti: str
    # Eski veya haricî analiz çıktılarını da kabul etmek için serbest metin
    # tutulur; varsayılan reel sektör modelidir.
    model_type: str = "real_economy"
    karar_gerekcesi: Optional[str] = None
    generated_at: datetime
