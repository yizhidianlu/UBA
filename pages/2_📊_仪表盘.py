"""Dashboard page with real-time PB monitoring."""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from src.database import get_session
from src.database.models import Asset, Signal, SignalStatus, PortfolioPosition
from src.services import StockPoolService, SignalEngine, RealtimeService

st.set_page_config(page_title="仪表盘 - 不败之地", page_icon="📊", layout="wide")

# Auto-refresh settings
REFRESH_INTERVAL = 30  # seconds

# Initialize session state
if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = datetime.now()
if 'auto_refresh' not in st.session_state:
    st.session_state.auto_refresh = False
if 'realtime_data' not in st.session_state:
    st.session_state.realtime_data = {}

# Header with refresh controls
col1, col2, col3 = st.columns([3, 1, 1])

with col1:
    st.title("📊 实时仪表盘")

with col2:
    auto_refresh = st.toggle("自动刷新", value=st.session_state.auto_refresh, help=f"每{REFRESH_INTERVAL}秒自动刷新")
    st.session_state.auto_refresh = auto_refresh

with col3:
    if st.button("🔄 刷新数据", use_container_width=True):
        st.session_state.last_refresh = datetime.now()
        st.rerun()

# Show last update time
st.caption(f"📡 最后更新: {st.session_state.last_refresh.strftime('%Y-%m-%d %H:%M:%S')}")

# Initialize services
session = get_session()
stock_service = StockPoolService(session)
signal_engine = SignalEngine(session)
realtime_service = RealtimeService()

# Get all stocks
stocks = stock_service.get_all_stocks()
stock_codes = [s.code for s in stocks]

# Fetch real-time data
if stock_codes:
    with st.spinner("获取实时数据..."):
        realtime_data = realtime_service.get_batch_quotes(stock_codes)
        st.session_state.realtime_data = realtime_data
        st.session_state.last_refresh = datetime.now()
else:
    realtime_data = {}

# Top metrics
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("股票池数量", f"{len(stocks)}")

with col2:
    open_signals = signal_engine.get_open_signals()
    st.metric("待处理信号", f"{len(open_signals)}")

with col3:
    positions = session.query(PortfolioPosition).filter(PortfolioPosition.position_pct > 0).all()
    total_position = sum(p.position_pct for p in positions)
    st.metric("总仓位", f"{total_position:.1f}%")

with col4:
    st.metric("持仓股票", f"{len(positions)}")

st.divider()

# Main content
col_left, col_right = st.columns([1, 1])

with col_left:
    st.subheader("📈 实时监控")

    if stocks and realtime_data:
        monitoring_data = []

        for stock in stocks:
            if not stock.threshold:
                continue

            quote = realtime_data.get(stock.code)
            current_pb = quote.pb if quote else None
            current_price = quote.price if quote else None
            change_pct = quote.change_pct if quote else 0

            buy_threshold = stock.threshold.buy_pb

            if current_pb:
                distance = ((current_pb - buy_threshold) / buy_threshold) * 100

                if current_pb <= buy_threshold:
                    status = "🟢 触发买入"
                    status_sort = 0
                elif stock.threshold.add_pb and current_pb <= stock.threshold.add_pb:
                    status = "🔵 触发加仓"
                    status_sort = 1
                elif stock.threshold.sell_pb and current_pb >= stock.threshold.sell_pb:
                    status = "🔴 触发卖出"
                    status_sort = 2
                else:
                    status = "⚪ 监控中"
                    status_sort = 3
            else:
                distance = None
                status = "❓ 无数据"
                status_sort = 4

            # Price change color
            if change_pct > 0:
                price_display = f"🔺 {current_price:.2f}" if current_price else "-"
            elif change_pct < 0:
                price_display = f"🔻 {current_price:.2f}" if current_price else "-"
            else:
                price_display = f"{current_price:.2f}" if current_price else "-"

            monitoring_data.append({
                "_sort": status_sort,
                "状态": status,
                "股票": stock.name,
                "代码": stock.code,
                "现价": price_display,
                "涨跌": f"{change_pct:+.2f}%" if change_pct else "-",
                "当前PB": f"{current_pb:.2f}" if current_pb else "-",
                "请客价": f"{buy_threshold:.2f}",
                "距离": f"{distance:+.1f}%" if distance is not None else "-"
            })

        if monitoring_data:
            # Sort by status (triggered first)
            monitoring_data.sort(key=lambda x: (x["_sort"], x.get("距离", "999")))

            # Remove sort key for display
            for item in monitoring_data:
                del item["_sort"]

            df = pd.DataFrame(monitoring_data)

            # Style the dataframe
            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                height=400
            )
        else:
            st.info("请先在股票池中添加股票并设置阈值")
    else:
        st.info("股票池为空或无法获取数据")

with col_right:
    st.subheader("🔔 今日信号")

    # Scan for new signals based on real-time data
    new_signals_count = 0
    if stocks and realtime_data:
        for stock in stocks:
            if not stock.threshold:
                continue

            quote = realtime_data.get(stock.code)
            if quote and quote.pb:
                # Check if signal should be triggered
                signal = signal_engine.check_triggers(stock)
                if signal:
                    new_signals_count += 1

    today_signals = signal_engine.get_today_signals()

    if today_signals:
        for signal in today_signals:
            asset = session.query(Asset).filter(Asset.id == signal.asset_id).first()
            if asset:
                quote = realtime_data.get(asset.code)

                with st.container():
                    status_icon = "🟢" if signal.status == SignalStatus.OPEN else "✅"
                    signal_icon = {"BUY": "🟢", "ADD": "🔵", "SELL": "🔴"}.get(signal.signal_type.value, "⚪")

                    col1, col2 = st.columns([3, 1])

                    with col1:
                        st.markdown(f"**{status_icon} {asset.name}** ({asset.code})")
                        st.markdown(f"{signal_icon} **{signal.signal_type.value}** | PB: {signal.pb:.2f}")

                        if quote:
                            realtime_pb = quote.pb
                            if realtime_pb:
                                st.caption(f"实时PB: {realtime_pb:.2f} | 价格: {quote.price:.2f}")

                    with col2:
                        if signal.status == SignalStatus.OPEN:
                            st.markdown("**待处理**")

                    st.divider()
    else:
        st.info("今日暂无信号")

    if st.button("🔍 扫描信号", use_container_width=True):
        with st.spinner("扫描中..."):
            new_signals = signal_engine.scan_all_stocks()
            if new_signals:
                st.success(f"发现 {len(new_signals)} 个新信号!")
                st.rerun()
            else:
                st.info("未发现新信号")

st.divider()

# Portfolio section
st.subheader("💼 持仓概览")

positions = session.query(PortfolioPosition).filter(PortfolioPosition.position_pct > 0).all()

if positions:
    col1, col2 = st.columns([1, 1])

    with col1:
        portfolio_data = []
        total_value_change = 0

        for pos in positions:
            asset = session.query(Asset).filter(Asset.id == pos.asset_id).first()
            if asset:
                quote = realtime_data.get(asset.code)
                current_price = quote.price if quote else None
                change_pct = quote.change_pct if quote else 0
                current_pb = quote.pb if quote else None

                # Calculate P&L if we have cost basis
                if pos.avg_cost and current_price:
                    pnl_pct = ((current_price - pos.avg_cost) / pos.avg_cost) * 100
                else:
                    pnl_pct = None

                portfolio_data.append({
                    "股票": asset.name,
                    "仓位": f"{pos.position_pct:.1f}%",
                    "现价": f"{current_price:.2f}" if current_price else "-",
                    "成本": f"{pos.avg_cost:.2f}" if pos.avg_cost else "-",
                    "盈亏": f"{pnl_pct:+.1f}%" if pnl_pct is not None else "-",
                    "今日": f"{change_pct:+.2f}%" if change_pct else "-",
                    "PB": f"{current_pb:.2f}" if current_pb else "-"
                })

        if portfolio_data:
            df = pd.DataFrame(portfolio_data)
            st.dataframe(df, use_container_width=True, hide_index=True)

    with col2:
        # Pie chart
        chart_data = []
        for pos in positions:
            asset = session.query(Asset).filter(Asset.id == pos.asset_id).first()
            if asset:
                chart_data.append({"名称": asset.name, "仓位": pos.position_pct})

        cash_pct = 100 - sum(p.position_pct for p in positions)
        chart_data.append({"名称": "现金", "仓位": cash_pct})

        fig = px.pie(chart_data, values="仓位", names="名称", hole=0.4)
        fig.update_traces(textposition='inside', textinfo='percent+label')
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=300)
        st.plotly_chart(fig, use_container_width=True)
else:
    st.info("暂无持仓")

session.close()

# Auto-refresh logic
if st.session_state.auto_refresh:
    import time
    time.sleep(REFRESH_INTERVAL)
    st.rerun()
