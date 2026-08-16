"""Kullanıcıya gösterilecek Türkçe etiketler tek merkezden yönetilir."""

REAL_ECONOMY_LABELS = {
    "karlilik": "Kârlılık", "finansal_saglik": "Finansal Sağlık",
    "borc_yuk": "Borç Yükü", "nakit_kalitesi": "Nakit Akış Kalitesi", "buyume": "Büyüme",
    "profitability": "Kârlılık", "leverage": "Borç Yükü", "valuation": "Değerleme",
    "growth_and_cash_quality": "Büyüme ve Nakit Akış Kalitesi",
}
FINANCIAL_INSTITUTION_LABELS = {
    "net_interest_margin": "Net Faiz Marjı", "profitability_roe": "Özkaynak Kârlılığı (ROE)",
    "capital_adequacy": "Sermaye Yeterliliği", "asset_quality": "Aktif Kalitesi (TGA)",
}
RECOMMENDATION_LABELS = {
    "guclu_al": "Güçlü Al", "al": "Al", "notr": "Nötr", "sat": "Sat", "guclu_sat": "Güçlü Sat",
    "GÜÇLÜ_AL": "Güçlü Al", "AL": "Al", "NÖTR": "Nötr", "SAT": "Sat", "GÜÇLÜ_SAT": "Güçlü Sat", "VERİ_YETERSİZ": "Veri Yetersiz",
}
RECOMMENDATION_COLORS = {
    "guclu_al": "#1E8E4F", "al": "#5FAE6E", "notr": "#B8A93A", "sat": "#D98A3D", "guclu_sat": "#C0392B",
    "GÜÇLÜ_AL": "#1E8E4F", "AL": "#5FAE6E", "NÖTR": "#B8A93A", "SAT": "#D98A3D", "GÜÇLÜ_SAT": "#C0392B", "VERİ_YETERSİZ": "#7F8C8D",
}

def get_labels_for_model(model_type: str) -> dict:
    return FINANCIAL_INSTITUTION_LABELS if model_type == "financial_institution" else REAL_ECONOMY_LABELS

def humanize_fallback(key: str) -> str:
    return key.replace("_", " ").strip().title()

def label_for(key: str, model_type: str = "real_economy") -> str:
    return get_labels_for_model(model_type).get(key, humanize_fallback(key))

def recommendation_label(code: str) -> str:
    return RECOMMENDATION_LABELS.get(code, humanize_fallback(code))

def recommendation_color(code: str) -> str:
    return RECOMMENDATION_COLORS.get(code, "#7F8C8D")
