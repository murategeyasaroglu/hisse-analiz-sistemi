import streamlit as st
import plotly.graph_objects as go

import analyzer as analysis_engine
import labels
from data_fetcher import fetch_live_company_payload, fetch_price_history
from news_fetcher import fetch_recent_news


def get_result_value(result, key: str, default=None):
    return result.get(key, default) if isinstance(result, dict) else getattr(result, key, default)


def get_sub_scores(result) -> dict:
    quantitative = get_result_value(result, "quantitative", {}) or {}
    return get_result_value(quantitative, "sub_scores", {}) or get_result_value(result, "kategori_ozet", {}) or {}


def get_qualitative_red_flags(result) -> list:
    qualitative = get_result_value(result, "qualitative_analysis", {}) or {}
    return get_result_value(qualitative, "red_flags", []) or get_result_value(result, "red_flags", []) or []


def turkish_confidence(value: object) -> str:
    return {"dusuk": "Düşük", "orta": "Orta", "yuksek": "Yüksek"}.get(str(value).lower(), "Düşük")


def recommendation_badge(code: object) -> str:
    normalized = str(code).lower()
    if normalized in {"guclu_al", "al"}:
        label, color = ("Güçlü Al" if normalized == "guclu_al" else "Al"), "#22C55E"
    elif normalized in {"guclu_sat", "sat"}:
        label, color = ("Güçlü Sat" if normalized == "guclu_sat" else "Sat"), "#EF4444"
    else:
        label, color = "Tut", "#F59E0B"
    return f'<div class="recommendation" style="border-color:{color};color:{color};"><span>ÖNERİ</span><strong>{label}</strong></div>'


def format_market_value(value, currency: str | None = None) -> str:
    if value is None:
        return "Veri yok"
    for divisor, suffix in ((1_000_000_000_000, "Tn"), (1_000_000_000, "Mr"), (1_000_000, "Mn")):
        if abs(value) >= divisor:
            return f"{value / divisor:.2f} {suffix} {currency or ''}".strip()
    return f"{value:,.0f} {currency or ''}".strip()


def build_price_chart(history, symbol: str, range_code: str) -> go.Figure:
    fig = go.Figure()
    yaxis_config = dict(showgrid=False, zeroline=False, side="right", title="Fiyat")
    if history is None or history.empty or "Close" not in history:
        fig.add_annotation(text="Bu zaman aralığı için fiyat verisi bulunamadı.", x=0.5, y=0.5, showarrow=False)
    else:
        close = history["Close"].dropna()
        reference_price = history.attrs.get("reference_close") if range_code == "1G" else float(close.iloc[0])
        reference_price = float(reference_price or close.iloc[0])
        period_change = (close / reference_price - 1) * 100
        net_change = float(period_change.iloc[-1])
        color = "#00C805" if net_change >= 0 else "#FF3B30"
        fill_color = "rgba(0,200,5,0.08)" if net_change >= 0 else "rgba(255,59,48,0.08)"
        ymin, ymax = float(close.min()), float(close.max())
        spread = ymax - ymin
        padding = max(spread * 0.02, abs(ymax) * 0.01, 0.01)
        ymin, ymax = ymin - padding, ymax + padding
        yaxis_config.update(autorange=False, range=[ymin, ymax])
        # Alt sınırı görünür fiyat bandına sabitleyen görünmez baz çizgisi,
        # ``tonexty`` alan dolgusunun sıfıra inmeden çizilmesini sağlar.
        fig.add_trace(go.Scatter(x=close.index, y=[ymin] * len(close), mode="lines", line=dict(width=0, color="rgba(0,0,0,0)"), hoverinfo="skip", showlegend=False))
        fig.add_trace(go.Scatter(
            x=close.index, y=close, mode="lines", name="Kapanış", line=dict(color=color, width=2.7),
            fill="tonexty", fillcolor=fill_color, customdata=[[value] for value in period_change],
            hovertemplate="<b>%{y:,.2f}</b><br>%{x|%d %b %Y, %H:%M}<br>Dönem başlangıcına göre: %{customdata[0]:+.2f}%<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=[close.index[-1]], y=[close.iloc[-1]], mode="markers", showlegend=False, hoverinfo="skip",
            marker=dict(size=9, color=color, line=dict(color="#F8FAFC", width=1.5)),
        ))
        reference_label = f"Önceki kapanış {reference_price:,.2f}" if range_code == "1G" else f"Başlangıç {reference_price:,.2f}"
        fig.add_shape(type="line", x0=0, x1=1, xref="paper", y0=reference_price, y1=reference_price, yref="y", line=dict(color="#94A3B8", width=1, dash="dot"))
        fig.add_annotation(x=1, y=reference_price, xref="paper", yref="y", xanchor="right", yanchor="bottom", text=reference_label, showarrow=False, font=dict(size=11, color="#CBD5E1"), bgcolor="rgba(17,24,39,0.75)")
    fig.update_layout(
        title=f"{symbol} · Fiyat Hareketi ({range_code})", template="plotly_dark", height=390,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=12, r=12, t=46, b=12),
        xaxis=dict(showgrid=False, zeroline=False),
        yaxis={**yaxis_config, "side": "left", "title": None, "showgrid": True, "gridcolor": "rgba(148,163,184,0.15)", "griddash": "dot"},
        showlegend=False,
    )
    return fig


def build_subscore_bar_chart(category_scores: dict[str, float], model_type: str) -> go.Figure:
    items = sorted(category_scores.items(), key=lambda item: item[1])
    names = [labels.label_for(key, model_type) for key, _ in items]
    values = [round(value, 1) for _, value in items]
    colors = ["#EF4444" if value < 40 else "#F59E0B" if value < 60 else "#22C55E" for value in values]
    fig = go.Figure(go.Bar(x=values, y=names, orientation="h", marker_color=colors, text=[f"{value:.1f}" for value in values], textposition="outside"))
    fig.update_layout(xaxis=dict(range=[0, 110], title="Skor (0-100)", gridcolor="#263244"), yaxis=dict(title=""), template="plotly_dark", paper_bgcolor="#111827", plot_bgcolor="#111827", height=max(260, 80 + 58 * len(names)), margin=dict(l=10, r=45, t=10, b=10), showlegend=False)
    return fig


def build_composite_gauge(score: float) -> go.Figure:
    fig = go.Figure(go.Indicator(mode="gauge", value=score, gauge={
        "axis": {"range": [0, 100], "tickwidth": 2, "tickfont": {"size": 13, "color": "#CBD5E1"}},
        "bar": {"color": "#38BDF8", "thickness": 0.34}, "bgcolor": "#111827",
        "steps": [{"range": [0, 40], "color": "#56252A"}, {"range": [40, 60], "color": "#5C4822"}, {"range": [60, 100], "color": "#1F5038"}],
        "threshold": {"line": {"color": "#F8FAFC", "width": 5}, "thickness": 0.9, "value": score},
    }, title={"text": "Hisse Etki Skoru", "font": {"size": 18, "color": "#E5E7EB"}}))
    for x, text, color in ((0.5, f"<b>{score:.1f}</b>", "#F8FAFC"), (0.5, "/ 100", "#94A3B8"), (0.14, "Riskli", "#F87171"), (0.50, "Nötr", "#FBBF24"), (0.86, "Olumlu", "#4ADE80")):
        y, size = (0.39, 42) if text.startswith("<b>") else ((0.25, 14) if text == "/ 100" else (0.07, 11))
        fig.add_annotation(x=x, y=y, xref="paper", yref="paper", text=text, showarrow=False, font=dict(size=size, color=color))
    fig.update_layout(template="plotly_dark", paper_bgcolor="#111827", height=330, margin=dict(l=20, r=20, t=48, b=5))
    return fig


st.set_page_config(page_title="Hisse Etki Terminali", page_icon="📈", layout="wide")
st.markdown("""<style>
.stApp { background:#0B1220; color:#E5E7EB; }
[data-testid="stMetric"] { background:#111827; border:1px solid #263244; border-radius:10px; padding:12px; }
.recommendation { background:#111827; border:1px solid; border-radius:10px; padding:10px; text-align:center; }
.recommendation span { display:block; font-size:11px; letter-spacing:1px; color:#94A3B8; }
.recommendation strong { display:block; font-size:22px; margin-top:2px; }
</style>""", unsafe_allow_html=True)

st.title("📈 Hisse Etki Terminali")
st.caption("Canlı fiyat, finansal skor ve küresel haber akışını tek panelde izleyin.")

input_col, button_col = st.columns([4, 1])
with input_col:
    ticker_input = st.text_input("Hisse sembolü", value="THYAO.IS", placeholder="THYAO.IS, GARAN.IS veya AAPL").upper()
with button_col:
    st.write("")
    analyze_button = st.button("Analiz Et", use_container_width=True, type="primary")

range_code = st.radio("Fiyat aralığı", ("1G", "5G", "1A", "6A", "YBK", "1Y", "5Y", "Maks."), index=2, horizontal=True, label_visibility="collapsed")

if analyze_button:
    with st.spinner(f"{ticker_input} canlı verileri hazırlanıyor..."):
        try:
            payload = fetch_live_company_payload(ticker_input)
            news = fetch_recent_news(ticker_input)
            payload["qualitative_events"] = news
            st.session_state["terminal_payload"] = payload
            st.session_state["terminal_result"] = analysis_engine.run_analysis(payload)
            st.session_state["terminal_news"] = news
            st.session_state["terminal_ticker"] = ticker_input
        except Exception as exc:
            st.error(f"Analiz sırasında bir hata oluştu: {exc}")

if st.session_state.get("terminal_result"):
    payload = st.session_state["terminal_payload"]
    result = st.session_state["terminal_result"]
    recent_news = st.session_state["terminal_news"]
    symbol = st.session_state["terminal_ticker"]
    market = payload.get("market_data", {})
    company = payload.get("company_identifier", {})
    score = float(get_result_value(result, "hisse_etki_skoru", 0.0))
    recommendation = get_result_value(result, "oneri", "notr")
    model_type = get_result_value(result, "model_type", "real_economy")

    st.divider()
    left_col, right_col = st.columns([3, 2], gap="large")
    with left_col:
        try:
            price_history = fetch_price_history(symbol, range_code)
            st.plotly_chart(build_price_chart(price_history, symbol, range_code), use_container_width=True)
        except Exception as exc:
            st.warning(f"Fiyat grafiği şu an yüklenemedi: {exc}")
    with right_col:
        st.subheader("Piyasa Özeti")
        currency = market.get("currency")
        price = market.get("current_price")
        change = market.get("daily_change_percent")
        price_text = f"{price:,.2f} {currency or ''}" if price is not None else "Veri yok"
        st.metric("Güncel Fiyat", price_text, f"{change:+.2f}%" if change is not None else None)
        st.metric("Sektör", company.get("sector_name") or company.get("industry") or "Veri yok")
        st.metric("Piyasa Değeri", format_market_value(market.get("market_cap"), currency))
        st.markdown(recommendation_badge(recommendation), unsafe_allow_html=True)
        score_col, confidence_col = st.columns(2)
        score_col.metric("Etki Skoru", f"{score:.1f}/100")
        confidence_col.metric("Güven Seviyesi", turkish_confidence(get_result_value(result, "guven_seviyesi", "dusuk")))

    st.divider()
    subscore_col, gauge_col = st.columns([3, 2], gap="large")
    with subscore_col:
        st.subheader("Kategori Alt-Skor Analizi")
        categories = get_sub_scores(result)
        if categories:
            st.plotly_chart(build_subscore_bar_chart(categories, model_type), use_container_width=True)
        else:
            st.info("Gösterilecek kategori skoru bulunamadı.")
    with gauge_col:
        st.plotly_chart(build_composite_gauge(score), use_container_width=True)

    st.subheader("Karar Gerekçesi")
    st.info(get_result_value(result, "karar_gerekcesi") or get_result_value(result, "analiz_ozeti", "Karar gerekçesi oluşturulamadı."))

    st.subheader("⚠️ Kırmızı Bayraklar")
    red_flags = get_qualitative_red_flags(result)
    if red_flags:
        for flag in red_flags:
            st.error(f"Tetiklenen kırmızı bayrak: {get_result_value(flag, 'trigger_condition', flag)}")
    else:
        st.success("Tetiklenen kırmızı bayrak bulunmadı.")

    st.subheader("Son Gelişmeler & Küresel Haberler")
    for event in recent_news:
        if event.get("is_placeholder"):
            st.info(event.get("summary", "Gündemde öne çıkan sıcak haber bulunamadı."))
            continue
        event_score = event.get("event_score", 0)
        icon = "🟢" if event_score > 0 else "🔴" if event_score < 0 else "🟡"
        st.markdown(f"{icon} **{event.get('title', 'Başlıksız haber')}**")
        st.caption(f"Duygu/etki skoru: {event_score:+.0f}/10 · {event.get('source', 'Haber akışı')}")
        st.write(event.get("summary", ""))

    with st.expander("Ham JSON çıktısını görüntüle"):
        st.json(result if isinstance(result, dict) else result.model_dump(mode="json"))
