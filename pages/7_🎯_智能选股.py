"""Smart stock screening page - background scan for undervalued stocks."""
import streamlit as st
import pandas as pd
from datetime import datetime

# Database imports
from src.database import get_session, init_db
from src.database.models import Market

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

from src.services import StockPoolService, AIAnalyzer
from src.ui import GLOBAL_CSS, APP_NAME_CN, APP_NAME_EN, render_header, render_footer

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
stock_service = StockPoolService(session)
scanner = get_scanner() if SCANNER_AVAILABLE else None

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
    扫描间隔可调整，避免触发API限制。
</div>
""", unsafe_allow_html=True)

# Get current progress
progress_info = scanner.get_progress() if scanner else None

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
        min_value=60,
        max_value=300,
        value=120,
        step=30,
        key="bg_interval",
        help="每只股票分析间隔，建议120秒以上避免API限制"
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

        # AI 评分显示
        if c.ai_score and c.ai_score > 0:
            ai_score_display = f"{'⭐' * c.ai_score} ({c.ai_score})"
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
                            # 同步 AI 评分
                            if c.ai_score:
                                stock_service.update_stock(
                                    c.code,
                                    ai_score=c.ai_score,
                                    ai_suggestion=c.ai_suggestion
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
                    StockCandidate.status == CandidateStatus.PENDING
                ).delete()
                session.commit()
                st.info("备选池已清空")
                st.rerun()

    # 手动更新 AI 评分
    st.divider()
    st.markdown("#### 🤖 AI 评分管理")

    # 找出未评分的股票
    unscored_candidates = [c for c in available_candidates if not c.ai_score]

    col1, col2 = st.columns(2)
    with col1:
        if unscored_candidates:
            st.caption(f"有 {len(unscored_candidates)} 只股票未获取 AI 评分")
            if st.button("🤖 为所有未评分股票获取AI评分", use_container_width=True):
                progress_bar = st.progress(0)
                status_text = st.empty()
                ai_analyzer = AIAnalyzer()

                if ai_analyzer.last_error:
                    st.error(ai_analyzer.last_error)
                else:
                    success_count = 0
                    for idx, c in enumerate(unscored_candidates):
                        progress_bar.progress((idx + 1) / len(unscored_candidates))
                        status_text.text(f"正在分析 {c.name} ({idx + 1}/{len(unscored_candidates)})...")

                        try:
                            fundamental = ai_analyzer.fetch_fundamental_data(c.code)
                            if fundamental:
                                report = ai_analyzer.generate_analysis_report(fundamental)
                                if report:
                                    c.ai_score = report.ai_score
                                    c.ai_suggestion = report.summary
                                    c.updated_at = datetime.now()
                                    success_count += 1
                        except Exception as e:
                            print(f"AI评分失败 {c.code}: {e}")

                    session.commit()
                    progress_bar.empty()
                    status_text.empty()

                    if success_count:
                        st.success(f"✅ 成功为 {success_count} 只股票获取 AI 评分！")
                        st.rerun()
                    else:
                        st.warning("未能获取任何评分")
        else:
            st.success("✅ 所有股票已完成 AI 评分")

    with col2:
        # 显示 AI 评分统计
        scored_count = len([c for c in available_candidates if c.ai_score])
        if scored_count > 0:
            avg_score = sum(c.ai_score for c in available_candidates if c.ai_score) / scored_count
            high_score_count = len([c for c in available_candidates if c.ai_score and c.ai_score >= 4])
            st.metric("平均 AI 评分", f"{avg_score:.1f} ⭐")
            st.caption(f"4分以上: {high_score_count} 只")
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
