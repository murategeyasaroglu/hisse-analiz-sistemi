"""Yahoo Finance ve Google News TR RSS haber toplama katmanı."""

from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen
from xml.etree import ElementTree

YAHOO_RSS_URL = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US"
GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search?q={query}&hl=tr&gl=TR&ceid=TR:tr"
POSITIVE_WORDS = ("beat", "growth", "upgrade", "record", "profit", "surge", "approval", "contract", "artış", "büyüme", "kâr", "anlaşma", "ihale")
NEGATIVE_WORDS = ("miss", "loss", "downgrade", "lawsuit", "risk", "decline", "probe", "warning", "zarar", "düşüş", "soruşturma", "ceza")


def fetch_recent_news(symbol: str, days: int = 7, limit: int = 12) -> list[dict[str, Any]]:
    """BIST için Google News TR/KAP, diğer hisseler için çoklu RSS haberi döndürür."""
    bare_symbol = symbol.upper().removesuffix(".IS")
    query = quote(f"{bare_symbol} hisse OR KAP")
    sources = [
        ("Google News TR", GOOGLE_NEWS_RSS_URL.format(query=query)),
        ("Yahoo Finance RSS", YAHOO_RSS_URL.format(symbol=quote(symbol.upper()))),
    ]
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    events: list[dict[str, Any]] = []
    seen: set[str] = set()

    for source, url in sources:
        for item in _read_rss(url):
            raw_title = _clean_title(item.findtext("title") or "", source)
            raw_summary = _clean_text(item.findtext("description") or item.findtext("summary") or "")
            published_at = _parse_date(item.findtext("pubDate"))
            if not raw_title or _is_irrelevant(raw_title, raw_summary) or (published_at and published_at < cutoff):
                continue
            duplicate_key = _dedupe_key(raw_title)
            if duplicate_key in seen:
                continue
            seen.add(duplicate_key)
            score = score_news_sentiment(f"{raw_title} {raw_summary}")
            summary = _short_turkish_summary(raw_summary, raw_title)
            events.append({
                # Gerçek RSS başlığı görünür kalır; hiçbir jenerik başlık üretilmez.
                "title": raw_title,
                "summary": summary,
                "raw_title": raw_title,
                "published_at": published_at.isoformat() if published_at else None,
                "event_score": score,
                "materiality_weight": min(1.0, 0.4 + abs(score) / 12),
                "source": source,
            })

    events.sort(key=lambda event: (abs(event["event_score"]), event["published_at"] or ""), reverse=True)
    if events:
        return events[:limit]
    return [{
        "title": f"{bare_symbol} için doğrulanmış yeni haber bulunamadı",
        "summary": "Son yedi günde erişilebilir bir haber kaynağı bulunamadı; haber etkisi nötr (0/10) kabul edildi.",
        "event_score": 0.0,
        "materiality_weight": 0.0,
        "source": "Bilgilendirme",
        "is_placeholder": True,
    }]


def score_news_sentiment(text: str) -> float:
    """Haber metni için açıklanabilir, -10 ile +10 sınırlı sözcük skoru."""
    lowered = text.lower()
    positive = sum(word in lowered for word in POSITIVE_WORDS)
    negative = sum(word in lowered for word in NEGATIVE_WORDS)
    return float(max(-10, min(10, (positive - negative) * 3)))


def _read_rss(url: str) -> list[ElementTree.Element]:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (stock-analysis-dashboard)"})
    try:
        with urlopen(request, timeout=10) as response:
            return ElementTree.fromstring(response.read()).findall(".//item")
    except Exception:
        return []


def _clean_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", html.unescape(value))
    return re.sub(r"\s+", " ", without_tags).strip()


def _clean_title(value: str, source: str) -> str:
    title = _clean_text(value)
    # Google News başlıklarının sonundaki yayıncı adını kaldırır; haber başlığı korunur.
    if source == "Google News TR" and " - " in title:
        title = title.rsplit(" - ", 1)[0].strip()
    return title


def _short_turkish_summary(summary: str, title: str) -> str:
    """RSS'in gerçek açıklamasını HTML'siz, en fazla iki cümleyle gösterir."""
    text = _clean_text(summary)
    if not text or _dedupe_key(text) == _dedupe_key(title):
        return title
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(sentences[:2])[:420].strip()


def _is_irrelevant(title: str, summary: str) -> bool:
    text = f"{title} {summary}".lower()
    return any(term in text for term in ("sponsorlu", "sponsored", "advertisement", "reklam", "cookies policy"))


def _dedupe_key(title: str) -> str:
    return re.sub(r"[^a-z0-9çğıöşü]", "", title.lower())[:120]


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None
