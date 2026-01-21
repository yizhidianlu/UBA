"""AI-powered fundamental analysis page using Gemini."""
import streamlit as st
from datetime import datetime, date, timedelta
from src.database import get_session
from src.database.models import Asset
from src.services import StockPoolService, AIAnalyzer, RealtimeService, ValuationService
from src.ui import GLOBAL_CSS, APP_NAME_CN, APP_NAME_EN, render_header, render_footer, render_alert

st.set_page_config(
    page_title=f"AI分析 - {APP_NAME_CN} | {APP_NAME_EN}",
    page_icon="🤖",
    layout="wide"
)

# Apply global styles
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

# Header
st.markdown(render_header("AI 基本面分析", "使用 Gemini AI 生成专业投资分析报告", "🤖"), unsafe_allow_html=True)

# Initialize services
session = get_session()
stock_service = StockPoolService(session)
valuation_service = ValuationService(session)
realtime_service = RealtimeService()

ai_analyzer = AIAnalyzer()

# Session state for reports
if 'current_report' not in st.session_state:
    st.session_state.current_report = None
if 'fundamental_data' not in st.session_state:
    st.session_state.fundamental_data = None

st.divider()

# ==================== Stock Selection ====================
col1, col2 = st.columns([2, 1])

with col1:
    st.markdown("### 📊 选择分析对象")

    # Option 1: Select from stock pool
    stocks = stock_service.get_all_stocks()

    tab1, tab2 = st.tabs(["从股票池选择", "输入股票代码"])

    with tab1:
        if stocks:
            stock_options = {f"{s.name} ({s.code})": s.code for s in stocks}
            selected_display = st.selectbox(
                "选择股票",
                options=list(stock_options.keys()),
                help="从已添加的股票池中选择"
            )
            selected_code = stock_options[selected_display] if selected_display else None
        else:
            st.info("股票池为空，请先添加股票或直接输入代码")
            selected_code = None

    with tab2:
        input_code = st.text_input(
            "股票代码",
            placeholder="输入股票代码，如 600519",
            help="支持A股代码"
        )
        if input_code:
            selected_code = input_code

with col2:
    st.markdown("### ⚙️ 分析选项")

    analysis_type = st.radio(
        "分析类型",
        ["完整报告", "快速分析"],
        help="完整报告包含详细的估值、基本面和风险分析"
    )

    include_pb_history = st.checkbox("包含PB历史分析", value=True)

st.divider()

# ==================== Generate Analysis ====================
if st.button("🚀 生成 AI 分析报告", type="primary", use_container_width=True):
    if not selected_code:
        st.error("请先选择或输入股票代码")
    else:
        with st.spinner("正在获取数据并生成分析报告，请稍候..."):
            try:
                # Fetch fundamental data
                fundamental = ai_analyzer.fetch_fundamental_data(selected_code)

                if not fundamental:
                    st.error("无法获取股票基本面数据，请检查代码是否正确")
                else:
                    st.session_state.fundamental_data = fundamental

                    if analysis_type == "快速分析":
                        # Quick analysis
                        quick_result = ai_analyzer.quick_analysis(selected_code)
                        if quick_result:
                            st.session_state.current_report = {
                                "type": "quick",
                                "content": quick_result,
                                "fundamental": fundamental
                            }
                        else:
                            error_msg = getattr(ai_analyzer, 'last_error', None) or "未知错误"
                            st.markdown(render_alert(f"AI 分析生成失败: {error_msg}", "danger"), unsafe_allow_html=True)
                    else:
                        # Full report
                        # Get PB history if available
                        pb_history = None
                        threshold_buy = None
                        threshold_add = None
                        threshold_sell = None

                        if include_pb_history:
                            # Try to get from database first
                            stock = stock_service.get_stock(selected_code)
                            if stock:
                                start_date = date.today() - timedelta(days=5*365)
                                valuations = valuation_service.get_pb_history(stock.id, start_date=start_date)
                                if valuations:
                                    pb_history = [{"date": v.date, "pb": v.pb} for v in valuations if v.pb]

                                if stock.threshold:
                                    threshold_buy = stock.threshold.buy_pb
                                    threshold_add = stock.threshold.add_pb
                                    threshold_sell = stock.threshold.sell_pb

                        report = ai_analyzer.generate_analysis_report(
                            fundamental=fundamental,
                            pb_history=pb_history,
                            threshold_buy=threshold_buy,
                            threshold_add=threshold_add,
                            threshold_sell=threshold_sell
                        )

                        if report:
                            st.session_state.current_report = {
                                "type": "full",
                                "report": report,
                                "fundamental": fundamental
                            }
                        else:
                            error_msg = getattr(ai_analyzer, 'last_error', None) or "未知错误"
                            st.markdown(render_alert(f"AI 分析报告生成失败: {error_msg}", "danger"), unsafe_allow_html=True)

            except Exception as e:
                st.error(f"分析过程出错: {e}")

# ==================== Display Results ====================
if st.session_state.current_report:
    report_data = st.session_state.current_report
    fundamental = report_data.get("fundamental")

    st.divider()

    # Display fundamental metrics
    st.markdown(f"### 📈 {fundamental.name} ({fundamental.code}) - 基本面数据")

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric("当前价格", f"¥{fundamental.current_price:.2f}" if fundamental.current_price else "N/A")
    with col2:
        st.metric("市盈率 PE", f"{fundamental.pe_ttm:.2f}" if fundamental.pe_ttm else "N/A")
    with col3:
        st.metric("市净率 PB", f"{fundamental.pb:.2f}" if fundamental.pb else "N/A")
    with col4:
        st.metric("市值(亿)", f"{fundamental.market_cap:.0f}" if fundamental.market_cap else "N/A")
    with col5:
        st.metric("行业", fundamental.industry or "N/A")

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        roe_display = f"{fundamental.roe:.2f}%" if fundamental.roe else "N/A"
        st.metric("ROE", roe_display)
    with col2:
        gm_display = f"{fundamental.gross_margin:.2f}%" if fundamental.gross_margin else "N/A"
        st.metric("毛利率", gm_display)
    with col3:
        dr_display = f"{fundamental.debt_ratio:.2f}%" if fundamental.debt_ratio else "N/A"
        st.metric("资产负债率", dr_display)
    with col4:
        rev_display = f"{fundamental.revenue_yoy:+.2f}%" if fundamental.revenue_yoy else "N/A"
        st.metric("营收同比", rev_display)
    with col5:
        profit_display = f"{fundamental.profit_yoy:+.2f}%" if fundamental.profit_yoy else "N/A"
        st.metric("利润同比", profit_display)

    st.divider()

    # Display AI analysis
    if report_data["type"] == "quick":
        st.markdown("### 🤖 AI 快速分析")
        st.markdown(f"""
        <div class="metric-card">
            {report_data["content"]}
        </div>
        """, unsafe_allow_html=True)

    else:
        report = report_data["report"]

        st.markdown("### 🤖 AI 投资分析报告")
        st.caption(f"生成时间: {report.generated_at.strftime('%Y-%m-%d %H:%M:%S')}")

        # Summary
        st.markdown("#### 💡 一句话总结")
        st.markdown(render_alert(report.summary, "info", "💡"), unsafe_allow_html=True)

        # Tabs for different sections
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📊 估值分析",
            "📈 基本面分析",
            "⚠️ 风险提示",
            "💰 投资建议",
            "📋 PB阈值建议"
        ])

        with tab1:
            st.markdown(f"""
            <div class="metric-card">
                {report.valuation_analysis}
            </div>
            """, unsafe_allow_html=True)

        with tab2:
            st.markdown(f"""
            <div class="metric-card">
                {report.fundamental_analysis}
            </div>
            """, unsafe_allow_html=True)

        with tab3:
            st.markdown(f"""
            <div class="metric-card">
                {report.risk_analysis}
            </div>
            """, unsafe_allow_html=True)

        with tab4:
            st.markdown(f"""
            <div class="metric-card">
                {report.investment_suggestion}
            </div>
            """, unsafe_allow_html=True)

        with tab5:
            st.markdown(f"""
            <div class="metric-card">
                {report.pb_recommendation}
            </div>
            """, unsafe_allow_html=True)

        # Full report expander
        with st.expander("📄 查看完整报告", expanded=False):
            st.markdown(report.full_report)

    # Action buttons
    st.divider()
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("🔄 重新分析", use_container_width=True):
            st.session_state.current_report = None
            st.rerun()

    with col2:
        # Check if stock is in pool
        stock_in_pool = stock_service.get_stock(fundamental.code)
        if not stock_in_pool:
            if st.button("➕ 添加到股票池", use_container_width=True):
                st.info("请前往股票池页面添加该股票")

    with col3:
        if st.button("📋 复制报告", use_container_width=True):
            if report_data["type"] == "full":
                st.code(report_data["report"].full_report)
            else:
                st.code(report_data["content"])

# ==================== Recent Analyses ====================
st.divider()
st.markdown("### 📚 股票池快速分析")

if stocks:
    # Get real-time data
    stock_codes = [s.code for s in stocks]
    realtime_data = realtime_service.get_batch_quotes(stock_codes)

    cols = st.columns(3)

    for idx, stock in enumerate(stocks[:6]):  # Show max 6 stocks
        col = cols[idx % 3]

        with col:
            quote = realtime_data.get(stock.code)

            change_color = "#E53935" if quote and quote.change_pct > 0 else "#43A047" if quote and quote.change_pct < 0 else "#666"
            change_icon = "▲" if quote and quote.change_pct > 0 else "▼" if quote and quote.change_pct < 0 else "―"

            st.markdown(f"""
            <div class="metric-card" style="margin-bottom: 1rem;">
                <strong>{stock.name}</strong> <span style="color: #666;">({stock.code})</span>
                {"<p style='margin: 0.5rem 0; color: #666;'>价格: ¥" + f"{quote.price:.2f}" + f" <span style='color: {change_color};'>{change_icon} {quote.change_pct:+.2f}%</span></p>" if quote else ""}
                {"<p style='margin: 0; color: #666;'>PB: " + f"{quote.pb:.2f}</p>" if quote and quote.pb else ""}
            </div>
            """, unsafe_allow_html=True)

            if st.button(f"分析 {stock.name}", key=f"analyze_{stock.code}", use_container_width=True):
                with st.spinner(f"正在分析 {stock.name}..."):
                    quick_result = ai_analyzer.quick_analysis(stock.code)
                    if quick_result:
                        st.markdown(quick_result)
                    else:
                        error_msg = getattr(ai_analyzer, 'last_error', None) or "未知错误"
                        st.warning(f"分析失败: {error_msg}")

else:
    st.info("股票池为空，请先添加股票")

# Footer
st.markdown(render_footer(), unsafe_allow_html=True)

session.close()
