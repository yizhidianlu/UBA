"""Smart stock screening page - background scan for undervalued stocks."""
import streamlit as st
import pandas as pd
from datetime import datetime

# Database imports
from src.database import get_session, init_db
from src.database.models import Market, AIAnalysisReport

# Import models for background scanning
try:
    from src.database.models import StockCandidate, ScanProgress, CandidateStatus
    from src.services.background_scanner import get_scanner
    SCANNER_AVAILABLE = True
except ImportError as e:
    print(f"Background scanner not available: {e}")
    SCANNER_AVAILABLE = False
    StockCandidate = None
    ScanProgress = None
    CandidateStatus = None
    get_scanner = None

from src.services import StockPoolService, AIAnalyzer
from src.ui import (
    GLOBAL_CSS, APP_NAME_CN, APP_NAME_EN, render_header, render_footer,
    require_auth, render_auth_sidebar, get_current_user_id
)


def sync_ai_report_to_database(session, user_id: int, code: str, name: str, ai_score: int, ai_suggestion: str):
    """同步AI评分到AIAnalysisReport表"""
    existing = session.query(AIAnalysisReport).filter(
        AIAnalysisReport.code == code,
        AIAnalysisReport.user_id == user_id
    ).first()
    if existing:
        # 更新现有记录
        existing.ai_score = ai_score
        existing.summary = ai_suggestion
        existing.updated_at = datetime.now()
    else:
        # 创建新记录（简化版，只保存评分和摘要）
        new_report = AIAnalysisReport(
            user_id=user_id,
            code=code,
            name=name,
            summary=ai_suggestion,
            ai_score=ai_score
        )
        session.add(new_report)
    session.commit()

st.set_page_config(
    page_title=f"智能选股 - {APP_NAME_CN} | {APP_NAME_EN}",
    page_icon="🎯",
    layout="wide"
)

# Apply global styles
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

# Header
st.markdown(render_header("智能选股", "后台扫描全市场低估股票", "🎯"), unsafe_allow_html=True)

# Initialize database and services
init_db()
session = get_session()
require_auth(session)
user_id = get_current_user_id()
with st.sidebar:
    render_auth_sidebar()
    st.divider()
stock_service = StockPoolService(session, user_id)
scanner = get_scanner(user_id) if SCANNER_AVAILABLE else None

st.divider()

# Check scanner availability
if not SCANNER_AVAILABLE:
    st.warning("⚠️ 后台扫描功能暂不可用，请稍后重试或刷新页面")
    st.stop()

st.markdown("### 🔄 全市场后台扫描")
st.markdown("""
<div style="background: #E3F2FD; padding: 1rem; border-radius: 8px; margin-bottom: 1rem;">
    <strong>💡 功能说明</strong><br>
    后台扫描器会按顺序分析A股所有股票，将符合条件的股票自动加入备选池。<br>
    <strong>🤖 AI评分：</strong>扫描器会自动为每只符合条件的股票进行AI评分，无需手动操作。<br>
    扫描间隔已固定为5秒/只股票。
</div>
""", unsafe_allow_html=True)

# Get current progress
progress_info = scanner.get_progress() if scanner else None

col1, col2 = st.columns(2)

with col1:
    st.markdown("#### ⚙️ 扫描设置")

    if "bg_distance" not in st.session_state:
        st.session_state["bg_distance"] = 5

    bg_max_distance = st.slider(
        "距请客价最大距离 (%)",
        min_value=5,
        max_value=50,
        step=5,
        key="bg_distance",
        help="PB距离请客价的百分比阈值"
    )

    bg_interval = 5  # 固定扫描间隔为5秒
    st.info("⏱️ 扫描间隔: 5秒/只股票")

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

if not progress_info:
    if scanner.start_scan(pb_threshold_pct=float(bg_max_distance), scan_interval=bg_interval):
        st.info("✅ 后台扫描已自动启动，可离开此页面。")
        st.rerun()

# Control buttons
st.divider()
col1, col2, col3, col4 = st.columns(4)

with col1:
    is_running = scanner.is_running()
    scan_completed = bool(progress_info) and not is_running and progress_info.get('total_stocks') and progress_info.get('current_index') == 0
    if scan_completed:
        if st.button("🔁 重新扫描", type="primary", use_container_width=True):
            if scanner.start_scan(pb_threshold_pct=float(bg_max_distance), scan_interval=bg_interval):
                st.success("✅ 已开始重新扫描！")
                st.rerun()
    else:
        st.info("自动扫描已启用")

with col2:
    resume_enabled = bool(progress_info) and not is_running and progress_info.get('total_stocks') and progress_info.get('current_index', 0) > 0
    if st.button("▶️ 恢复扫描", use_container_width=True, disabled=not resume_enabled):
        if scanner.start_scan(pb_threshold_pct=float(bg_max_distance), scan_interval=bg_interval):
            st.success("✅ 扫描已恢复")
            st.rerun()

with col3:
    if st.button("⏹️ 停止扫描", use_container_width=True):
        scanner.stop_scan()
        st.info("扫描已停止")
        st.rerun()

with col4:
    if st.button("🔄 刷新状态", use_container_width=True):
        st.rerun()

# AI评分独立控制
st.divider()
st.markdown("### 🤖 AI评分线程")
st.caption("💡 备选池出现股票时自动开始评分，按添加时间从早到晚依次评分")

ai_control_supported = hasattr(scanner, "is_ai_scoring_running")
col1, col2 = st.columns(2)

with col1:
    ai_running = scanner.is_ai_scoring_running() if ai_control_supported else False
    if not ai_control_supported:
        st.markdown("""
        <div style="background: #FFF3E0; padding: 0.5rem; border-radius: 8px; text-align: center;">
            <strong>⚠️ AI线程未启用</strong>
        </div>
        """, unsafe_allow_html=True)
    elif ai_running:
        st.markdown("""
        <div style="background: #E8F5E9; padding: 0.5rem; border-radius: 8px; text-align: center;">
            <strong>🟢 AI评分运行中</strong>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="background: #FFF3E0; padding: 0.5rem; border-radius: 8px; text-align: center;">
            <strong>⏸️ AI评分等待中</strong>
        </div>
        """, unsafe_allow_html=True)

with col2:
    st.info("🧠 自动评分已启用，无需手动启动")

if not ai_control_supported:
    st.warning("当前运行环境尚未更新AI评分线程功能，请先部署最新的服务端代码。")

st.divider()

# ==================== Candidate Pool ====================
st.markdown("### 📋 备选池")

# Get candidates
candidates = session.query(StockCandidate).filter(
    StockCandidate.status == CandidateStatus.PENDING,
    StockCandidate.user_id == user_id
).order_by(StockCandidate.pb_distance_pct).all()

if candidates:
    st.markdown(f"**找到 {len(candidates)} 只待处理股票**")

    existing_stocks = {s.code for s in stock_service.get_all_stocks()}

    candidate_data = []
    for c in candidates:
        in_pool = c.code in existing_stocks
        distance_icon = "🟢" if c.pb_distance_pct <= 0 else "🟡" if c.pb_distance_pct <= 10 else "🟠"

        # AI 评分显示
        if c.ai_score and c.ai_score > 0:
            ai_score_display = f"{c.ai_score}分"
        else:
            ai_score_display = "未评分"

        candidate_data.append({
            "状态": "✅ 已加入" if in_pool else "⬜ 待处理",
            "距离": f"{distance_icon} {c.pb_distance_pct:+.1f}%",
            "代码": c.code,
            "名称": c.name,
            "行业": c.industry or "-",
            "现价": f"¥{c.current_price:.2f}" if c.current_price else "-",
            "当前PB": f"{c.current_pb:.2f}" if c.current_pb else "-",
            "请客价PB": f"{c.recommended_buy_pb:.2f}" if c.recommended_buy_pb else "-",
            "AI评分": ai_score_display,
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
                            # 使用推荐的阈值
                            add_pb = c.recommended_add_pb if c.recommended_add_pb else c.min_pb
                            sell_pb = c.recommended_sell_pb if c.recommended_sell_pb else c.avg_pb

                            asset = stock_service.add_stock(
                                code=c.code,
                                name=c.name,
                                market=Market.A_SHARE,
                                industry=c.industry,
                                competence_score=3,
                                notes=f"后台扫描推荐 - 距请客价{c.pb_distance_pct:+.1f}%",
                                buy_pb=c.recommended_buy_pb,
                                add_pb=add_pb,
                                sell_pb=sell_pb
                            )
                            # 同步 AI 评分到 Asset 表
                            if c.ai_score:
                                stock_service.update_stock(
                                    c.code,
                                    ai_score=c.ai_score,
                                    ai_suggestion=c.ai_suggestion
                                )
                                # 同步 AI 评分到 AIAnalysisReport 表
                                sync_ai_report_to_database(
                                    session, user_id, c.code, c.name,
                                    c.ai_score, c.ai_suggestion
                                )
                            c.status = CandidateStatus.ADDED
                            success += 1
                        except Exception as e:
                            print(f"添加股票失败 {c.code}: {e}")
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
                    StockCandidate.status == CandidateStatus.PENDING,
                    StockCandidate.user_id == user_id
                ).delete()
                session.commit()
                st.info("备选池已清空")
                st.rerun()

    # AI 评分统计
    st.divider()
    st.markdown("#### 🤖 AI 评分统计")

    scored_candidates = [c for c in available_candidates if c.ai_score and c.ai_score > 0]
    unscored_candidates = [c for c in available_candidates if not c.ai_score]

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("已评分", f"{len(scored_candidates)} 只")

    with col2:
        if scored_candidates:
            avg_score = sum(c.ai_score for c in scored_candidates) / len(scored_candidates)
            st.metric("平均评分", f"{avg_score:.1f}分")
        else:
            st.metric("平均评分", "-")

    with col3:
        high_score_count = len([c for c in scored_candidates if c.ai_score >= 80])
        st.metric("高分(≥80)", f"{high_score_count} 只")

    if unscored_candidates:
        st.caption(f"💡 有 {len(unscored_candidates)} 只股票待评分，后台扫描时会自动进行AI评分")
else:
    st.info("备选池为空，启动后台扫描后符合条件的股票会自动加入")

# Show ignored/added history
with st.expander("📜 历史记录"):
    col1, col2 = st.columns(2)

    with col1:
        added = session.query(StockCandidate).filter(
            StockCandidate.status == CandidateStatus.ADDED,
            StockCandidate.user_id == user_id
        ).count()
        st.metric("已添加", f"{added} 只")

    with col2:
        ignored = session.query(StockCandidate).filter(
            StockCandidate.status == CandidateStatus.IGNORED,
            StockCandidate.user_id == user_id
        ).count()
        st.metric("已忽略", f"{ignored} 只")

    if st.button("🗑️ 清空所有历史"):
        session.query(StockCandidate).filter(
            StockCandidate.user_id == user_id
        ).delete()
        session.query(ScanProgress).filter(
            ScanProgress.user_id == user_id
        ).delete()
        session.commit()
        st.success("历史已清空")
        st.rerun()

# Footer
st.markdown(render_footer(), unsafe_allow_html=True)

session.close()
