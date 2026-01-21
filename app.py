"""Main Streamlit application entry point for UBA (Unbeaten Area) - 不败之地."""
import streamlit as st
import textwrap
from datetime import datetime, date

# Import UI styles
from src.ui import (
    GLOBAL_CSS, APP_NAME_CN, APP_NAME_EN, APP_FULL_NAME, APP_SLOGAN,
    render_main_header, render_metric_card, render_alert, render_footer
)

# Import database modules
from src.database import init_db, get_session
from src.database.models import Asset, Signal, SignalStatus, PortfolioPosition, VisitLog

st.set_page_config(
    page_title=f"{APP_NAME_CN} | {APP_NAME_EN}",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Apply global styles
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

# Initialize database on first run
init_db()

def get_today_visits(db_session) -> int:
    """Get and increment today's visit count."""
    today = date.today()
    visit_log = db_session.query(VisitLog).filter(VisitLog.visit_date == today).first()
    if visit_log:
        visit_log.count += 1
    else:
        visit_log = VisitLog(visit_date=today, count=1)
        db_session.add(visit_log)
    db_session.commit()
    return visit_log.count

# Render main header
st.markdown(render_main_header(), unsafe_allow_html=True)
from src.services import RealtimeService

session = get_session()
realtime_service = RealtimeService()

# Get basic stats
stocks = session.query(Asset).all()
stock_codes = [s.code for s in stocks]

# Fetch real-time data
if stock_codes:
    realtime_data = realtime_service.get_batch_quotes(stock_codes)
else:
    realtime_data = {}

# Stats Section
st.markdown("### 📊 系统概览")

col1, col2, col3, col4 = st.columns(4)

with col1:
    stock_count = len(stocks)
    st.markdown(render_metric_card(f"{stock_count} 只", "股票池", "📋"), unsafe_allow_html=True)

with col2:
    open_signals = session.query(Signal).filter(Signal.status == SignalStatus.OPEN).count()
    st.markdown(render_metric_card(f"{open_signals} 个", "待处理信号", "🔔"), unsafe_allow_html=True)

with col3:
    positions = session.query(PortfolioPosition).filter(PortfolioPosition.position_pct > 0).all()
    total_position = sum(p.position_pct for p in positions)
    st.markdown(render_metric_card(f"{total_position:.1f}%", "总仓位", "💼"), unsafe_allow_html=True)

with col4:
    cash_position = 100 - total_position
    st.markdown(render_metric_card(f"{cash_position:.1f}%", "现金比例", "💰"), unsafe_allow_html=True)

st.divider()

# Triggered alerts
st.markdown("### ⚡ 实时触发提醒")

triggered_stocks = []
for stock in stocks:
    if not stock.threshold:
        continue

    quote = realtime_data.get(stock.code)
    if quote and quote.pb:
        current_pb = quote.pb
        buy_pb = stock.threshold.buy_pb

        if current_pb <= buy_pb:
            triggered_stocks.append({
                "type": "BUY",
                "name": stock.name,
                "code": stock.code,
                "current_pb": current_pb,
                "threshold": buy_pb,
                "price": quote.price,
                "change_pct": quote.change_pct
            })
        elif stock.threshold.add_pb and current_pb <= stock.threshold.add_pb:
            triggered_stocks.append({
                "type": "ADD",
                "name": stock.name,
                "code": stock.code,
                "current_pb": current_pb,
                "threshold": stock.threshold.add_pb,
                "price": quote.price,
                "change_pct": quote.change_pct
            })
        elif stock.threshold.sell_pb and current_pb >= stock.threshold.sell_pb:
            triggered_stocks.append({
                "type": "SELL",
                "name": stock.name,
                "code": stock.code,
                "current_pb": current_pb,
                "threshold": stock.threshold.sell_pb,
                "price": quote.price,
                "change_pct": quote.change_pct
            })

if triggered_stocks:
    for item in triggered_stocks:
        icon_map = {"BUY": "🟢", "ADD": "🟡", "SELL": "🔴"}
        action_map = {"BUY": "买入", "ADD": "加仓", "SELL": "卖出"}
        type_map = {"BUY": "success", "ADD": "warning", "SELL": "danger"}

        icon = icon_map.get(item["type"], "⚪")
        action = action_map.get(item["type"], "")
        alert_type = type_map.get(item["type"], "info")

        change_str = f"+{item['change_pct']:.2f}%" if item['change_pct'] > 0 else f"{item['change_pct']:.2f}%"

        message = f"""
        <strong>{item['name']}</strong> ({item['code']}) 触发 <strong>{action}</strong> 信号！<br>
        当前 PB: <strong>{item['current_pb']:.2f}</strong> | 阈值: {item['threshold']:.2f} |
        价格: ¥{item['price']:.2f} ({change_str})
        """
        st.markdown(render_alert(message, alert_type, icon), unsafe_allow_html=True)
else:
    st.markdown(render_alert("📡 实时监控中，暂无触发信号", "info"), unsafe_allow_html=True)

st.divider()

# Navigation guide
st.markdown("### 🚀 快速导航")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown(textwrap.dedent("""
    <div class="metric-card">
        <h4>📋 股票池</h4>
        <ul style="color: #666; margin: 0; padding-left: 1.2rem;">
            <li>添加/删除股票</li>
            <li>设置 PB 阈值</li>
            <li>自动分析推荐</li>
        </ul>
    </div>
    """), unsafe_allow_html=True)

with col2:
    st.markdown(textwrap.dedent("""
    <div class="metric-card">
        <h4>📊 仪表盘</h4>
        <ul style="color: #666; margin: 0; padding-left: 1.2rem;">
            <li>实时 PB 监控</li>
            <li>自动刷新数据</li>
            <li>信号状态一览</li>
        </ul>
    </div>
    """), unsafe_allow_html=True)

with col3:
    st.markdown(textwrap.dedent("""
    <div class="metric-card">
        <h4>🎯 智能选股</h4>
        <ul style="color: #666; margin: 0; padding-left: 1.2rem;">
            <li>一键筛选低估股</li>
            <li>PB 接近请客价</li>
            <li>批量加入股票池</li>
        </ul>
    </div>
    """), unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown(textwrap.dedent("""
    <div class="metric-card">
        <h4>🔔 信号中心</h4>
        <ul style="color: #666; margin: 0; padding-left: 1.2rem;">
            <li>处理触发信号</li>
            <li>执行四动作</li>
            <li>记录交易日志</li>
        </ul>
    </div>
    """), unsafe_allow_html=True)

with col2:
    st.markdown(textwrap.dedent("""
    <div class="metric-card">
        <h4>💼 持仓管理</h4>
        <ul style="color: #666; margin: 0; padding-left: 1.2rem;">
            <li>查看当前持仓</li>
            <li>盈亏分析</li>
            <li>风险控制</li>
        </ul>
    </div>
    """), unsafe_allow_html=True)

with col3:
    st.markdown(textwrap.dedent("""
    <div class="metric-card">
        <h4>🧠 AI 分析</h4>
        <ul style="color: #666; margin: 0; padding-left: 1.2rem;">
            <li>智能投资建议</li>
            <li>基本面分析</li>
            <li>估值诊断</li>
        </ul>
    </div>
    """), unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)
st.info("👈 使用左侧导航栏进入各功能模块")

# Footer
st.markdown(render_footer(), unsafe_allow_html=True)

# Get today's visit count
today_visits = get_today_visits(session)

# Sidebar branding
with st.sidebar:
    st.markdown(textwrap.dedent(f"""
    <div style="text-align: center; padding: 1rem 0;">
        <div style="font-size: 2.5rem;">🛡️</div>
        <div style="font-size: 1.2rem; font-weight: 700; color: #1E88E5;">{APP_NAME_CN}</div>
        <div style="font-size: 0.8rem; color: #666;">{APP_NAME_EN} • {APP_FULL_NAME}</div>
    </div>
    """), unsafe_allow_html=True)

    st.divider()

    st.caption(f"⏰ 更新时间: {datetime.now().strftime('%H:%M:%S')}")

    if st.button("🔄 刷新数据", use_container_width=True):
        st.rerun()

    st.divider()
    st.caption(f"👀 今日访问: {today_visits} 次")

session.close()
