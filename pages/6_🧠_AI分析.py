"""AI-powered fundamental analysis page using Qwen3-max."""
import streamlit as st
from datetime import datetime, date, timedelta
from src.database import get_session, init_db
from src.database.models import Asset, AIAnalysisReport
from src.services import StockPoolService, AIAnalyzer, RealtimeService, ValuationService
from src.ui import GLOBAL_CSS, APP_NAME_CN, APP_NAME_EN, render_header, render_footer, render_alert

st.set_page_config(
    page_title=f"AI分析 - {APP_NAME_CN} | {APP_NAME_EN}",
    page_icon="🧠",
    layout="wide"
)

# Apply global styles
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

# Header
st.markdown(render_header("AI 基本面分析", "使用 Qwen3-max 生成专业投资分析报告", "🧠"), unsafe_allow_html=True)

# Initialize services
init_db()
session = get_session()
stock_service = StockPoolService(session)
valuation_service = ValuationService(session)
realtime_service = RealtimeService()

ai_analyzer = AIAnalyzer()

# Session state
if 'current_report' not in st.session_state:
    st.session_state.current_report = None
if 'fundamental_data' not in st.session_state:
    st.session_state.fundamental_data = None
if 'show_history' not in st.session_state:
    st.session_state.show_history = True
if 'selected_report_code' not in st.session_state:
    st.session_state.selected_report_code = None
if 'auto_generate_report_code' not in st.session_state:
    st.session_state.auto_generate_report_code = None
if 'ai_input_code' not in st.session_state:
    st.session_state.ai_input_code = ""

st.divider()


def get_historical_report(code: str):
    """获取历史分析报告"""
    return session.query(AIAnalysisReport).filter(
        AIAnalysisReport.code == code
    ).order_by(AIAnalysisReport.created_at.desc()).first()


def save_report(report, fundamental):
    """保存分析报告到数据库"""
    # 检查是否已存在该股票的报告
    existing = session.query(AIAnalysisReport).filter(
        AIAnalysisReport.code == fundamental.code
    ).first()

    if existing:
        # 更新现有报告
        existing.name = fundamental.name
        existing.summary = report.summary
        existing.valuation_analysis = report.valuation_analysis
        existing.fundamental_analysis = report.fundamental_analysis
        existing.risk_analysis = report.risk_analysis
        existing.investment_suggestion = report.investment_suggestion
        existing.pb_recommendation = report.pb_recommendation
        existing.full_report = report.full_report
        existing.ai_score = report.ai_score
        existing.price_at_report = fundamental.current_price
        existing.pb_at_report = fundamental.pb
        existing.pe_at_report = fundamental.pe_ttm
        existing.market_cap_at_report = fundamental.market_cap
        existing.updated_at = datetime.now()
    else:
        # 创建新报告
        new_report = AIAnalysisReport(
            code=fundamental.code,
            name=fundamental.name,
            summary=report.summary,
            valuation_analysis=report.valuation_analysis,
            fundamental_analysis=report.fundamental_analysis,
            risk_analysis=report.risk_analysis,
            investment_suggestion=report.investment_suggestion,
            pb_recommendation=report.pb_recommendation,
            full_report=report.full_report,
            ai_score=report.ai_score,
            price_at_report=fundamental.current_price,
            pb_at_report=fundamental.pb,
            pe_at_report=fundamental.pe_ttm,
            market_cap_at_report=fundamental.market_cap
        )
        session.add(new_report)

    session.commit()


def generate_new_report(selected_code, include_pb_history=True):
    """生成新的AI分析报告"""
    fundamental = ai_analyzer.fetch_fundamental_data(selected_code)

    if not fundamental:
        return None, "无法获取股票基本面数据，请检查代码是否正确"

    # Get PB history if available
    pb_history = None
    threshold_buy = None
    threshold_add = None
    threshold_sell = None

    if include_pb_history:
        stock = stock_service.get_stock(selected_code)
        if stock:
            start_date = date.today() - timedelta(days=5 * 365)
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
        # 保存报告
        save_report(report, fundamental)
        return {"report": report, "fundamental": fundamental}, None
    else:
        error_msg = getattr(ai_analyzer, 'last_error', None) or "未知错误"
        return None, f"AI 分析报告生成失败: {error_msg}"


# ==================== Stock Selection ====================
col1, col2 = st.columns([2, 1])

with col1:
    st.markdown("### 📊 选择分析对象")

    stocks = stock_service.get_all_stocks()
    selected_report_code = st.session_state.selected_report_code
    selected_code = selected_report_code

    tab1, tab2 = st.tabs(["从股票池选择", "输入股票代码"])

    with tab1:
        if stocks:
            stock_options = {f"{s.name} ({s.code})": s.code for s in stocks}
            default_display = None
            if selected_report_code:
                for display, code in stock_options.items():
                    if code == selected_report_code:
                        default_display = display
                        break
            option_list = list(stock_options.keys())
            if default_display and st.session_state.get("ai_stock_select") != default_display:
                st.session_state["ai_stock_select"] = default_display
            default_index = option_list.index(default_display) if default_display in option_list else 0
            selected_display = st.selectbox(
                "选择股票",
                options=option_list,
                index=default_index,
                key="ai_stock_select",
                help="从已添加的股票池中选择"
            )
            if default_display:
                selected_code = stock_options[selected_display] if selected_display else None
        else:
            st.info("股票池为空，请先添加股票或直接输入代码")
            selected_code = selected_report_code

    with tab2:
        if selected_report_code and selected_report_code != st.session_state.ai_input_code:
            st.session_state.ai_input_code = selected_report_code

        input_code = st.text_input(
            "股票代码",
            key="ai_input_code",
            placeholder="输入股票代码，如 600519",
            help="支持A股代码"
        )
        if input_code:
            selected_code = input_code
            if st.button("🚀 生成 AI 分析报告", type="primary", use_container_width=True):
                st.session_state.auto_generate_report_code = input_code
                st.session_state.selected_report_code = input_code
                st.rerun()

    if selected_code:
        st.session_state.selected_report_code = selected_code

with col2:
    st.markdown("### ⚙️ 分析选项")
    include_pb_history = st.checkbox("包含PB历史分析", value=True)

st.divider()

# ==================== Check Historical Report ====================
auto_generate_code = st.session_state.auto_generate_report_code
if auto_generate_code and auto_generate_code != selected_code:
    selected_code = auto_generate_code
    st.session_state.selected_report_code = auto_generate_code

if selected_code:
    if st.session_state.auto_generate_report_code:
        st.session_state.auto_generate_report_code = None
        with st.spinner("正在获取数据并生成分析报告，请稍候..."):
            result, error = generate_new_report(selected_code, include_pb_history)
            if result:
                st.success("✅ 报告生成成功！")
                st.rerun()
            else:
                st.error(error)

    historical_report = get_historical_report(selected_code)

    if historical_report:
        # 有历史报告
        report_age = datetime.now() - historical_report.updated_at
        days_old = report_age.days

        # 显示历史报告信息
        col1, col2, col3 = st.columns([2, 1, 1])

        with col1:
            st.markdown(f"### 📄 {historical_report.name} 分析报告")
            if days_old == 0:
                time_str = "今天"
            elif days_old == 1:
                time_str = "昨天"
            else:
                time_str = f"{days_old} 天前"

            st.caption(f"📅 报告生成时间: {historical_report.updated_at.strftime('%Y-%m-%d %H:%M')} ({time_str})")

            # 报告时的数据快照
            if historical_report.price_at_report:
                pb_str = f"{historical_report.pb_at_report:.2f}" if historical_report.pb_at_report else "N/A"
                pe_str = f"{historical_report.pe_at_report:.2f}" if historical_report.pe_at_report else "N/A"
                st.caption(
                    f"📊 报告时数据: 价格 ¥{historical_report.price_at_report:.2f} | PB {pb_str} | PE {pe_str}"
                )

        with col2:
            if historical_report.ai_score:
                st.metric("AI 评分", f"{'⭐' * historical_report.ai_score} ({historical_report.ai_score}分)")

        with col3:
            if st.button("🔄 更新报告", type="primary", use_container_width=True):
                with st.spinner("正在生成新的分析报告..."):
                    result, error = generate_new_report(selected_code, include_pb_history)
                    if result:
                        st.success("✅ 报告已更新！")
                        st.rerun()
                    else:
                        st.error(error)

        st.divider()

        # 显示报告内容
        # Summary
        st.markdown("#### 💡 一句话总结")
        st.markdown(render_alert(historical_report.summary or "暂无总结", "info", "💡"), unsafe_allow_html=True)

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
                {historical_report.valuation_analysis or "暂无估值分析"}
            </div>
            """, unsafe_allow_html=True)

        with tab2:
            st.markdown(f"""
            <div class="metric-card">
                {historical_report.fundamental_analysis or "暂无基本面分析"}
            </div>
            """, unsafe_allow_html=True)

        with tab3:
            st.markdown(f"""
            <div class="metric-card">
                {historical_report.risk_analysis or "暂无风险分析"}
            </div>
            """, unsafe_allow_html=True)

        with tab4:
            st.markdown(f"""
            <div class="metric-card">
                {historical_report.investment_suggestion or "暂无投资建议"}
            </div>
            """, unsafe_allow_html=True)

        with tab5:
            st.markdown(f"""
            <div class="metric-card">
                {historical_report.pb_recommendation or "暂无PB建议"}
            </div>
            """, unsafe_allow_html=True)

        # Full report expander
        with st.expander("📄 查看完整报告", expanded=False):
            st.markdown(historical_report.full_report or "暂无完整报告")

    else:
        # 没有历史报告
        st.info(f"📋 暂无 {selected_code} 的分析报告")

        if st.button("🚀 生成 AI 分析报告", type="primary", use_container_width=True):
            with st.spinner("正在获取数据并生成分析报告，请稍候..."):
                result, error = generate_new_report(selected_code, include_pb_history)
                if result:
                    st.success("✅ 报告生成成功！")
                    st.rerun()
                else:
                    st.error(error)

# ==================== All Reports History ====================
st.divider()
st.markdown("### 📚 历史分析报告")

all_reports = session.query(AIAnalysisReport).order_by(AIAnalysisReport.updated_at.desc()).limit(10).all()

if all_reports:
    for report in all_reports:
        report_age = datetime.now() - report.updated_at
        days_old = report_age.days

        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])

        with col1:
            st.markdown(f"**{report.name}** ({report.code})")

        with col2:
            if report.ai_score and report.ai_score > 0:
                st.markdown(f"{'⭐' * report.ai_score}")
            else:
                st.markdown("-")

        with col3:
            if days_old == 0:
                st.caption("今天")
            elif days_old == 1:
                st.caption("昨天")
            else:
                st.caption(f"{days_old}天前")

        with col4:
            if st.button("查看", key=f"view_{report.id}", use_container_width=True):
                # 这里可以设置 selected_code 来查看报告
                st.session_state.selected_report_code = report.code
                st.rerun()
else:
    st.info("暂无历史分析报告，请先选择股票进行分析")

# Footer
st.markdown(render_footer(), unsafe_allow_html=True)

session.close()
