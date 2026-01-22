"""Smart stock screening page - find undervalued stocks based on PB."""
import streamlit as st
import pandas as pd
from datetime import datetime
from src.database import get_session, init_db
from src.database.models import Market, StockCandidate, ScanProgress, CandidateStatus
from src.services import StockPoolService, ValuationService, StockScreener, StockAnalyzer, get_scanner
from src.ui import GLOBAL_CSS, APP_NAME_CN, APP_NAME_EN, render_header, render_footer, render_alert

st.set_page_config(
    page_title=f"智能选股 - {APP_NAME_CN} | {APP_NAME_EN}",
    page_icon="🎯",
    layout="wide"
)

# Apply global styles
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

# Header
st.markdown(render_header("智能选股", "一键筛选 / 后台扫描全市场低估股票", "🎯"), unsafe_allow_html=True)

# Initialize database and services
init_db()
session = get_session()
stock_service = StockPoolService(session)
valuation_service = ValuationService(session)

@st.cache_resource
def get_screener():
    return StockScreener()

@st.cache_resource
def get_analyzer():
    return StockAnalyzer()

screener = get_screener()
analyzer = get_analyzer()
scanner = get_scanner()

# Session state
if 'recommendations' not in st.session_state:
    st.session_state.recommendations = None
if 'selected_stocks' not in st.session_state:
    st.session_state.selected_stocks = set()

st.divider()

# ==================== Tabs ====================
tab1, tab2 = st.tabs(["🚀 一键选股", "🔄 后台扫描"])

# ==================== Tab 1: Quick Scan ====================
with tab1:
    st.markdown("### ⚙️ 筛选参数")

    col1, col2, col3 = st.columns(3)

    with col1:
        max_distance = st.slider(
            "距请客价最大距离 (%)",
            min_value=5,
            max_value=50,
            value=20,
            step=5,
            help="当前PB与推荐请客价的最大偏离百分比"
        )

    with col2:
        result_limit = st.selectbox(
            "返回数量",
            options=[5, 10, 15, 20],
            index=1,
            help="返回的股票数量"
        )

    with col3:
        st.write("")
        st.write("")
        scan_btn = st.button("🚀 一键智能选股", type="primary", use_container_width=True)

    st.divider()

    # Scanning
    if scan_btn:
        st.session_state.selected_stocks = set()

        progress_bar = st.progress(0)
        status_text = st.empty()

        def update_progress(current, total, message):
            progress_bar.progress(current / total)
            status_text.text(f"[{current}/{total}] {message}")

        with st.spinner("正在扫描市场，请稍候..."):
            try:
                recommendations = screener.scan_stocks(
                    max_distance_pct=float(max_distance),
                    limit=result_limit,
                    progress_callback=update_progress
                )
                st.session_state.recommendations = recommendations

                progress_bar.progress(1.0)
                status_text.text(f"扫描完成！找到 {len(recommendations)} 只符合条件的股票")

            except Exception as e:
                st.error(f"扫描失败: {e}")
                st.session_state.recommendations = None

    # Display Results
    if st.session_state.recommendations:
        recommendations = st.session_state.recommendations

        st.markdown(f"### 📊 筛选结果 ({len(recommendations)} 只)")

        if not recommendations:
            st.info("未找到符合条件的股票，请尝试调整筛选参数")
        else:
            existing_stocks = {s.code for s in stock_service.get_all_stocks()}

            data = []
            for idx, rec in enumerate(recommendations):
                in_pool = rec.code in existing_stocks
                distance_icon = "🟢" if rec.pb_distance_pct <= 0 else "🟡" if rec.pb_distance_pct <= 10 else "🟠"

                data.append({
                    "序号": idx + 1,
                    "状态": "✅ 已加入" if in_pool else "⬜ 未加入",
                    "距离": f"{distance_icon} {rec.pb_distance_pct:+.1f}%",
                    "代码": rec.code,
                    "名称": rec.name,
                    "行业": rec.industry or "-",
                    "现价": f"¥{rec.current_price:.2f}",
                    "当前PB": f"{rec.current_pb:.2f}",
                    "请客价PB": f"{rec.recommended_buy_pb:.2f}",
                    "市值(亿)": f"{rec.market_cap:.0f}" if rec.market_cap else "-",
                })

            df = pd.DataFrame(data)
            st.dataframe(df, use_container_width=True, hide_index=True, height=400)

            # Add selected
            available_stocks = [rec for rec in recommendations if rec.code not in existing_stocks]

            if available_stocks:
                st.divider()
                st.markdown("### ➕ 选择性加入股票池")

                selected_codes = st.multiselect(
                    "选择要添加的股票",
                    options=[f"{rec.name} ({rec.code})" for rec in available_stocks],
                    default=[]
                )

                if st.button("✅ 添加选中股票", type="primary") and selected_codes:
                    success_count = 0
                    for selection in selected_codes:
                        code = selection.split('(')[-1].replace(')', '').strip()
                        rec = next((r for r in available_stocks if r.code == code), None)
                        if rec:
                            try:
                                stock_service.add_stock(
                                    code=rec.code,
                                    name=rec.name,
                                    market=Market.A_SHARE,
                                    industry=rec.industry,
                                    competence_score=3,
                                    notes=f"智能选股推荐 - 距请客价{rec.pb_distance_pct:+.1f}%",
                                    buy_pb=rec.recommended_buy_pb,
                                    add_pb=rec.min_pb,
                                    sell_pb=rec.avg_pb
                                )
                                success_count += 1
                            except Exception:
                                pass

                    if success_count > 0:
                        st.success(f"✅ 成功添加 {success_count} 只股票！")
                        st.rerun()

# ==================== Tab 2: Background Scan ====================
with tab2:
    st.markdown("### 🔄 全市场后台扫描")
    st.markdown("""
    <div style="background: #E3F2FD; padding: 1rem; border-radius: 8px; margin-bottom: 1rem;">
        <strong>💡 功能说明</strong><br>
        后台扫描器会按顺序分析A股所有股票，将符合条件的股票自动加入备选池。<br>
        扫描间隔可调整，避免触发API限制。
    </div>
    """, unsafe_allow_html=True)

    # Get current progress
    progress_info = scanner.get_progress()

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### ⚙️ 扫描设置")

        bg_max_distance = st.slider(
            "距请客价最大距离 (%)",
            min_value=5,
            max_value=50,
            value=20,
            step=5,
            key="bg_distance",
            help="PB距离请客价的百分比阈值"
        )

        bg_interval = st.slider(
            "扫描间隔 (秒)",
            min_value=10,
            max_value=120,
            value=30,
            step=10,
            key="bg_interval",
            help="每只股票分析间隔，建议30秒以上避免限制"
        )

    with col2:
        st.markdown("#### 📊 扫描状态")

        if progress_info:
            is_running = scanner.is_running()

            if is_running:
                st.markdown(f"""
                <div style="background: #E8F5E9; padding: 1rem; border-radius: 8px;">
                    <strong>🟢 扫描进行中</strong><br>
                    进度: {progress_info['current_index']}/{progress_info['total_stocks']} ({progress_info['progress_pct']:.1f}%)<br>
                    最近扫描: {progress_info['last_scanned_code'] or '-'}
                </div>
                """, unsafe_allow_html=True)

                st.progress(progress_info['progress_pct'] / 100)
            else:
                st.markdown(f"""
                <div style="background: #FFF3E0; padding: 1rem; border-radius: 8px;">
                    <strong>⏸️ 扫描已暂停</strong><br>
                    上次进度: {progress_info['current_index']}/{progress_info['total_stocks']}<br>
                    可继续扫描
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("尚未开始扫描")

    # Control buttons
    st.divider()
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("▶️ 开始扫描", type="primary", use_container_width=True):
            if scanner.start_scan(pb_threshold_pct=float(bg_max_distance), scan_interval=bg_interval):
                st.success("✅ 后台扫描已启动！")
                st.info("扫描将在后台持续进行，可以离开此页面。")
                st.rerun()
            else:
                st.warning("扫描已在运行中")

    with col2:
        if st.button("⏹️ 停止扫描", use_container_width=True):
            scanner.stop_scan()
            st.info("扫描已停止")
            st.rerun()

    with col3:
        if st.button("🔄 刷新状态", use_container_width=True):
            st.rerun()

    st.divider()

    # ==================== Candidate Pool ====================
    st.markdown("### 📋 备选池")

    # Get candidates
    candidates = session.query(StockCandidate).filter(
        StockCandidate.status == CandidateStatus.PENDING
    ).order_by(StockCandidate.pb_distance_pct).all()

    if candidates:
        st.markdown(f"**找到 {len(candidates)} 只待处理股票**")

        existing_stocks = {s.code for s in stock_service.get_all_stocks()}

        candidate_data = []
        for c in candidates:
            in_pool = c.code in existing_stocks
            distance_icon = "🟢" if c.pb_distance_pct <= 0 else "🟡" if c.pb_distance_pct <= 10 else "🟠"

            candidate_data.append({
                "状态": "✅ 已加入" if in_pool else "⬜ 待处理",
                "距离": f"{distance_icon} {c.pb_distance_pct:+.1f}%",
                "代码": c.code,
                "名称": c.name,
                "行业": c.industry or "-",
                "现价": f"¥{c.current_price:.2f}" if c.current_price else "-",
                "当前PB": f"{c.current_pb:.2f}" if c.current_pb else "-",
                "请客价PB": f"{c.recommended_buy_pb:.2f}" if c.recommended_buy_pb else "-",
                "扫描时间": c.scanned_at.strftime("%m-%d %H:%M") if c.scanned_at else "-"
            })

        df_candidates = pd.DataFrame(candidate_data)
        st.dataframe(df_candidates, use_container_width=True, hide_index=True, height=300)

        # Batch operations
        st.divider()

        available_candidates = [c for c in candidates if c.code not in existing_stocks]

        if available_candidates:
            selected_candidates = st.multiselect(
                "选择要加入股票池的股票",
                options=[f"{c.name} ({c.code})" for c in available_candidates],
                default=[]
            )

            col1, col2, col3 = st.columns(3)

            with col1:
                if st.button("✅ 添加选中到股票池", type="primary", use_container_width=True) and selected_candidates:
                    success = 0
                    for sel in selected_candidates:
                        code = sel.split('(')[-1].replace(')', '').strip()
                        c = next((x for x in available_candidates if x.code == code), None)
                        if c:
                            try:
                                stock_service.add_stock(
                                    code=c.code,
                                    name=c.name,
                                    market=Market.A_SHARE,
                                    industry=c.industry,
                                    competence_score=3,
                                    notes=f"后台扫描推荐 - 距请客价{c.pb_distance_pct:+.1f}%",
                                    buy_pb=c.recommended_buy_pb,
                                    add_pb=c.min_pb,
                                    sell_pb=c.avg_pb
                                )
                                c.status = CandidateStatus.ADDED
                                success += 1
                            except Exception:
                                pass
                    session.commit()
                    if success:
                        st.success(f"✅ 成功添加 {success} 只股票！")
                        st.rerun()

            with col2:
                if st.button("🗑️ 忽略选中", use_container_width=True) and selected_candidates:
                    for sel in selected_candidates:
                        code = sel.split('(')[-1].replace(')', '').strip()
                        c = next((x for x in available_candidates if x.code == code), None)
                        if c:
                            c.status = CandidateStatus.IGNORED
                    session.commit()
                    st.info("已忽略选中股票")
                    st.rerun()

            with col3:
                if st.button("🧹 清空备选池", use_container_width=True):
                    session.query(StockCandidate).filter(
                        StockCandidate.status == CandidateStatus.PENDING
                    ).delete()
                    session.commit()
                    st.info("备选池已清空")
                    st.rerun()
    else:
        st.info("备选池为空，启动后台扫描后符合条件的股票会自动加入")

    # Show ignored/added history
    with st.expander("📜 历史记录"):
        col1, col2 = st.columns(2)

        with col1:
            added = session.query(StockCandidate).filter(
                StockCandidate.status == CandidateStatus.ADDED
            ).count()
            st.metric("已添加", f"{added} 只")

        with col2:
            ignored = session.query(StockCandidate).filter(
                StockCandidate.status == CandidateStatus.IGNORED
            ).count()
            st.metric("已忽略", f"{ignored} 只")

        if st.button("🗑️ 清空所有历史"):
            session.query(StockCandidate).delete()
            session.query(ScanProgress).delete()
            session.commit()
            st.success("历史已清空")
            st.rerun()

# Footer
st.markdown(render_footer(), unsafe_allow_html=True)

session.close()
