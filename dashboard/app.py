"""
Roboto — Dashboard Streamlit
Monitora o bot em tempo real: sinal atual, trades, métricas e gráfico de candles.

Uso:
    python -m streamlit run dashboard/app.py
"""

import time
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

API_URL = "http://localhost:8000"
REFRESH_INTERVAL = 10  # segundos

st.set_page_config(
    page_title="Roboto Dashboard",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ----------------------------------------------------------
# SIDEBAR
# ----------------------------------------------------------
with st.sidebar:
    st.title("🤖 Roboto")
    st.markdown("---")

    symbol   = st.selectbox("Par",       ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"], index=0)
    interval = st.selectbox("Timeframe", ["1m", "5m", "15m", "1h"], index=1)
    balance  = st.number_input("Saldo inicial ($)", value=10000.0, step=500.0)
    only_strong = st.checkbox("Só sinais FORTES", value=True)

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("▶ Iniciar", use_container_width=True, type="primary"):
            try:
                requests.post(f"{API_URL}/bot/start", json={
                    "symbol": symbol, "interval": interval,
                    "balance": balance, "only_strong": only_strong,
                }, timeout=5)
                st.success("Bot iniciado!")
            except Exception:
                st.error("API offline")
    with col2:
        if st.button("⏹ Parar", use_container_width=True):
            try:
                requests.post(f"{API_URL}/bot/stop", timeout=5)
                st.warning("Bot parado.")
            except Exception:
                st.error("API offline")

    if st.button("🔄 Retomar (pós-drawdown)", use_container_width=True):
        try:
            requests.post(f"{API_URL}/bot/resume", timeout=5)
            st.info("Bot retomado.")
        except Exception:
            st.error("API offline")

    st.markdown("---")
    auto_refresh = st.checkbox("Auto-refresh", value=True)
    st.caption(f"Atualiza a cada {REFRESH_INTERVAL}s")

# ----------------------------------------------------------
# HELPERS
# ----------------------------------------------------------

def fetch(endpoint: str) -> dict:
    try:
        r = requests.get(f"{API_URL}{endpoint}", timeout=5)
        return r.json()
    except Exception:
        return {}


def status_badge(running: bool, paused: bool) -> str:
    if paused:
        return "🟡 PAUSADO"
    if running:
        return "🟢 RODANDO"
    return "🔴 PARADO"


# ----------------------------------------------------------
# DADOS
# ----------------------------------------------------------
status  = fetch("/status")
signal  = fetch("/signal")
trades  = fetch("/trades")
metrics = fetch("/metrics")
candles = fetch(f"/candles?symbol={symbol}&interval={interval}&limit=100")

# ----------------------------------------------------------
# HEADER
# ----------------------------------------------------------
st.title("🤖 Roboto — Dashboard")
st.caption(f"Atualizado em {datetime.now().strftime('%H:%M:%S')}")

# ----------------------------------------------------------
# KPIs
# ----------------------------------------------------------
k1, k2, k3, k4, k5 = st.columns(5)

with k1:
    running = status.get("running", False)
    paused  = status.get("paused", False)
    st.metric("Status", status_badge(running, paused))

with k2:
    bal = status.get("balance")
    ini = status.get("initial_balance")
    delta = f"{((bal - ini) / ini * 100):+.2f}%" if bal and ini else None
    st.metric("Saldo", f"${bal:,.2f}" if bal else "—", delta=delta)

with k3:
    dd = status.get("drawdown_pct")
    st.metric("Drawdown", f"{dd:.1f}%" if dd is not None else "—", delta_color="inverse")

with k4:
    m = metrics.get("metrics") or metrics
    wr = m.get("win_rate")
    st.metric("Win Rate", f"{wr:.1f}%" if wr else "—")

with k5:
    pf = m.get("profit_factor")
    st.metric("Profit Factor", f"{pf:.2f}" if pf else "—")

st.markdown("---")

# ----------------------------------------------------------
# SINAL ATUAL + TRADE ABERTO
# ----------------------------------------------------------
col_sig, col_trade = st.columns([1, 1])

with col_sig:
    st.subheader("📡 Último Sinal")
    sig_data = signal.get("signal")
    if sig_data:
        EMOJIS = {
            "CALL_FORTE": "✅ CALL FORTE",
            "PUT_FORTE":  "✅ PUT FORTE",
            "CALL_FRACO": "⚠️ CALL FRACO",
            "PUT_FRACO":  "⚠️ PUT FRACO",
            "AGUARDAR":   "⏸️ AGUARDAR",
        }
        final = sig_data.get("final", "")
        st.markdown(f"### {EMOJIS.get(final, final)}")
        sc1, sc2, sc3 = st.columns(3)
        sc1.metric("Preço",     f"${sig_data.get('current_price', 0):,.2f}")
        sc2.metric("RSI",       f"{sig_data.get('rsi', 0):.2f}")
        sc3.metric("Confiança", f"{sig_data.get('confidence', 0):.0%}")
        st.caption(f"Sentiment: {sig_data.get('sentiment_signal')} ({sig_data.get('sentiment_score', 0):.2f})")
        st.caption(f"Técnico: {sig_data.get('technical_signal')} | {sig_data.get('reason', '')}")
    else:
        st.info("Nenhum sinal ainda. Inicie o bot.")

with col_trade:
    st.subheader("💼 Trade Aberto")
    ot = status.get("open_trade")
    if ot:
        tc1, tc2 = st.columns(2)
        tc1.metric("Direção",    ot["direction"])
        tc2.metric("Entrada",    f"${ot['entry_price']:,.2f}")
        tc1.metric("Stop Loss",  f"${ot['stop_loss']:,.2f}", delta_color="inverse")
        tc2.metric("Take Profit",f"${ot['take_profit']:,.2f}")
        st.caption(f"Aberto em: {ot.get('opened_at', '')}")
    else:
        st.info("Nenhum trade aberto no momento.")

st.markdown("---")

# ----------------------------------------------------------
# GRÁFICO DE CANDLES
# ----------------------------------------------------------
st.subheader(f"📈 {symbol} {interval} — Candlestick")
candle_list = candles.get("candles", [])
if candle_list:
    df_c = pd.DataFrame(candle_list)
    # A API retorna a coluna como open_time
    time_col = "open_time" if "open_time" in df_c.columns else df_c.columns[0]
    df_c[time_col] = pd.to_datetime(df_c[time_col])

    fig = go.Figure(data=[
        go.Candlestick(
            x=df_c[time_col],
            open=df_c["open"],
            high=df_c["high"],
            low=df_c["low"],
            close=df_c["close"],
            name="Preço",
            increasing_line_color="#00c853",
            decreasing_line_color="#ff1744",
        )
    ])
    fig.update_layout(
        height=400,
        margin=dict(l=0, r=0, t=30, b=0),
        xaxis_rangeslider_visible=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(gridcolor="#333333"),
        yaxis=dict(gridcolor="#333333"),
        font=dict(color="white"),
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Aguardando dados de candles...")

st.markdown("---")

# ----------------------------------------------------------
# TABELA DE TRADES
# ----------------------------------------------------------
st.subheader("📋 Histórico de Trades")
trades_list = trades.get("trades", [])
if trades_list:
    df_t = pd.DataFrame(trades_list)
    df_t["pnl_pct"] = df_t["pnl_pct"].apply(lambda x: f"{x:+.2f}%" if x is not None else "—")
    df_t["result"]  = df_t["result"].apply(
        lambda x: "✅ WIN" if x == "WIN" else ("❌ LOSS" if x == "LOSS" else "⏳")
    )
    cols = ["id", "symbol", "direction", "strength", "entry_price", "exit_price", "pnl_pct", "result", "opened_at"]
    st.dataframe(df_t[[c for c in cols if c in df_t.columns]], use_container_width=True, hide_index=True)
else:
    st.info("Nenhum trade fechado ainda.")

st.markdown("---")

# ----------------------------------------------------------
# MÉTRICAS DETALHADAS
# ----------------------------------------------------------
st.subheader("📊 Métricas de Performance")
m = metrics.get("metrics") or metrics
if m and m.get("total_trades"):
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("Total Trades", m["total_trades"])
    mc2.metric("Wins / Losses", f"{m['wins']}W / {m['losses']}L")
    mc3.metric("PnL Total",    f"{m['total_pnl_pct']:+.2f}%")
    mc4.metric("Sharpe Ratio", f"{m['sharpe_ratio']:.2f}")
    if m.get("approved"):
        st.success("✅ Estratégia APROVADA")
    else:
        st.warning("⚠️ Estratégia ainda não atingiu todas as metas")
else:
    st.info("Métricas disponíveis após o primeiro trade fechado.")

# ----------------------------------------------------------
# AUTO-REFRESH
# ----------------------------------------------------------
if auto_refresh:
    time.sleep(REFRESH_INTERVAL)
    st.rerun()
