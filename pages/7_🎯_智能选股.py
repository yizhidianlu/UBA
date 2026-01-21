"""Smart stock screening page - find undervalued stocks based on PB."""
import streamlit as st
import pandas as pd
from datetime import datetime
from src.database import get_session
from src.database.models import Market
from src.services import StockPoolService, ValuationService, StockScreener, StockAnalyzer
from src.ui import GLOBAL_CSS, APP_NAME_CN, APP_NAME_EN, render_header, render_footer, render_alert

st.set_page_config(
    page_title=f"智能选股 - {APP_NAME_CN} | {APP_NAME_EN}",
    page_icon="🎯",
    layout="wide"
)

# Apply global styles
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

# Header
st.markdown(render_header("智能选股", "一键筛选PB接近请客价的优质股票", "🎯"), unsafe_allow_html=True)

# Initialize services
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

# Session state for recommendations
if 'recommendations' not in st.session_state:
    st.session_state.recommendations = None
if 'selected_stocks' not in st.session_state:
    st.session_state.selected_stocks = set()

st.divider()

# ==================== Screening Parameters ====================
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

# ==================== Scanning ====================
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

# ==================== Display Results ====================
if st.session_state.recommendations:
    recommendations = st.session_state.recommendations

    st.markdown(f"### 📊 筛选结果 ({len(recommendations)} 只)")

    if not recommendations:
        st.info("未找到符合条件的股票，请尝试调整筛选参数")
    else:
        # Get existing stocks in pool
        existing_stocks = {s.code for s in stock_service.get_all_stocks()}

        # Build display data
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
                "最低PB": f"{rec.min_pb:.2f}",
                "平均PB": f"{rec.avg_pb:.2f}",
                "市值(亿)": f"{rec.market_cap:.0f}" if rec.market_cap else "-",
                "PE": f"{rec.pe_ttm:.1f}" if rec.pe_ttm else "-",
            })

        df = pd.DataFrame(data)

        # Display legend
        st.markdown("""
        <div style="background: #F5F5F5; padding: 0.75rem 1rem; border-radius: 8px; margin-bottom: 1rem;">
            <strong>📌 距离说明：</strong>
            <span style="color: #4CAF50;">🟢 已触发请客价</span> |
            <span style="color: #FFC107;">🟡 距离<10%</span> |
            <span style="color: #FF9800;">🟠 距离<20%</span>
        </div>
        """, unsafe_allow_html=True)

        st.dataframe(df, use_container_width=True, hide_index=True, height=400)

        st.divider()

        # ==================== Selective Addition ====================
        st.markdown("### ➕ 选择性加入股票池")

        # Filter out already added stocks
        available_stocks = [rec for rec in recommendations if rec.code not in existing_stocks]

        if not available_stocks:
            st.markdown(render_alert("所有推荐股票都已在股票池中！", "success", "🎉"), unsafe_allow_html=True)
        else:
            st.markdown(f"**可添加的股票 ({len(available_stocks)} 只)**")

            # Multi-select
            col1, col2 = st.columns([3, 1])

            with col1:
                selected_codes = st.multiselect(
                    "选择要添加的股票",
                    options=[f"{rec.name} ({rec.code})" for rec in available_stocks],
                    default=[],
                    help="可多选，然后一键添加到股票池"
                )

            with col2:
                st.write("")
                st.write("")
                add_selected_btn = st.button("✅ 添加选中", type="primary", use_container_width=True)

            # Quick select buttons
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("🔝 选择前3只", use_container_width=True):
                    st.session_state.quick_select = [f"{rec.name} ({rec.code})" for rec in available_stocks[:3]]
                    st.rerun()
            with col2:
                if st.button("📊 选择前5只", use_container_width=True):
                    st.session_state.quick_select = [f"{rec.name} ({rec.code})" for rec in available_stocks[:5]]
                    st.rerun()
            with col3:
                if st.button("🎯 全部选择", use_container_width=True):
                    st.session_state.quick_select = [f"{rec.name} ({rec.code})" for rec in available_stocks]
                    st.rerun()

            # Handle quick select
            if 'quick_select' in st.session_state:
                selected_codes = st.session_state.quick_select
                del st.session_state.quick_select

            # Add selected stocks
            if add_selected_btn and selected_codes:
                success_count = 0
                fail_count = 0

                progress = st.progress(0)
                for idx, selection in enumerate(selected_codes):
                    # Extract code from selection string
                    code = selection.split('(')[-1].replace(')', '').strip()

                    # Find the recommendation
                    rec = next((r for r in available_stocks if r.code == code), None)
                    if not rec:
                        fail_count += 1
                        continue

                    try:
                        # Add to stock pool
                        asset = stock_service.add_stock(
                            code=rec.code,
                            name=rec.name,
                            market=Market.A_SHARE,
                            industry=rec.industry if rec.industry else None,
                            competence_score=3,
                            notes=f"智能选股推荐 - 距请客价{rec.pb_distance_pct:+.1f}%",
                            buy_pb=rec.recommended_buy_pb,
                            add_pb=rec.min_pb,  # 使用最低PB作为加仓价
                            sell_pb=rec.avg_pb  # 使用平均PB作为退出价
                        )

                        # Fetch and save PB history
                        pb_data = analyzer.fetch_pb_history(rec.code, years=3)
                        if pb_data:
                            for d in pb_data[:500]:  # Limit to 500 data points
                                if d.get('pb'):
                                    try:
                                        valuation_service.save_valuation(
                                            asset_id=asset.id,
                                            val_date=d['date'],
                                            pb=d['pb'],
                                            data_source="screener"
                                        )
                                    except Exception:
                                        pass

                        success_count += 1

                    except Exception as e:
                        print(f"添加失败 {code}: {e}")
                        fail_count += 1

                    progress.progress((idx + 1) / len(selected_codes))

                if success_count > 0:
                    st.success(f"✅ 成功添加 {success_count} 只股票到股票池！")
                if fail_count > 0:
                    st.warning(f"⚠️ {fail_count} 只股票添加失败（可能已存在）")

                st.rerun()

        st.divider()

        # ==================== Individual Stock Cards ====================
        st.markdown("### 📋 股票详情")

        for rec in recommendations:
            in_pool = rec.code in existing_stocks

            with st.expander(
                f"{'✅' if in_pool else '⬜'} {rec.name} ({rec.code}) - 距离请客价 {rec.pb_distance_pct:+.1f}%",
                expanded=False
            ):
                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    st.metric("当前价格", f"¥{rec.current_price:.2f}")
                    st.metric("当前PB", f"{rec.current_pb:.2f}")

                with col2:
                    st.metric("推荐请客价", f"{rec.recommended_buy_pb:.2f}")
                    delta = rec.current_pb - rec.recommended_buy_pb
                    st.metric("PB差值", f"{delta:+.2f}", delta=f"{rec.pb_distance_pct:+.1f}%")

                with col3:
                    st.metric("历史最低PB", f"{rec.min_pb:.2f}")
                    st.metric("历史平均PB", f"{rec.avg_pb:.2f}")

                with col4:
                    st.metric("市值(亿)", f"{rec.market_cap:.0f}" if rec.market_cap else "N/A")
                    st.metric("PE(TTM)", f"{rec.pe_ttm:.1f}" if rec.pe_ttm else "N/A")

                st.markdown(f"**行业:** {rec.industry or '未知'}")

                if not in_pool:
                    if st.button(f"➕ 添加 {rec.name} 到股票池", key=f"add_{rec.code}"):
                        try:
                            asset = stock_service.add_stock(
                                code=rec.code,
                                name=rec.name,
                                market=Market.A_SHARE,
                                industry=rec.industry if rec.industry else None,
                                competence_score=3,
                                notes=f"智能选股推荐 - 距请客价{rec.pb_distance_pct:+.1f}%",
                                buy_pb=rec.recommended_buy_pb,
                                add_pb=rec.min_pb,
                                sell_pb=rec.avg_pb
                            )

                            # Fetch and save PB history
                            with st.spinner("正在获取历史数据..."):
                                pb_data = analyzer.fetch_pb_history(rec.code, years=3)
                                if pb_data:
                                    for d in pb_data[:500]:
                                        if d.get('pb'):
                                            try:
                                                valuation_service.save_valuation(
                                                    asset_id=asset.id,
                                                    val_date=d['date'],
                                                    pb=d['pb'],
                                                    data_source="screener"
                                                )
                                            except Exception:
                                                pass

                            st.success(f"✅ 已添加 {rec.name}")
                            st.rerun()

                        except ValueError as e:
                            st.error(str(e))
                        except Exception as e:
                            st.error(f"添加失败: {e}")
                else:
                    st.info("✅ 已在股票池中")

else:
    # Initial state - show instructions
    st.markdown("""
    <div class="metric-card">
        <h4>📖 使用说明</h4>
        <ol style="color: #666; margin: 0.5rem 0; padding-left: 1.2rem;">
            <li><strong>调整筛选参数</strong>：设置距请客价的最大距离百分比和返回数量</li>
            <li><strong>点击"一键智能选股"</strong>：系统将扫描预设的优质股票池</li>
            <li><strong>查看推荐结果</strong>：按距离请客价排序，越接近越靠前</li>
            <li><strong>选择性添加</strong>：勾选想要跟踪的股票，批量加入股票池</li>
        </ol>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("""
        <div class="metric-card">
            <h4>💡 筛选逻辑</h4>
            <ul style="color: #666; margin: 0.5rem 0; padding-left: 1.2rem;">
                <li><strong>请客价 (买入PB)</strong>：历史PB的25%分位数</li>
                <li><strong>距离计算</strong>：(当前PB - 请客价) / 请客价 × 100%</li>
                <li><span style="color: #4CAF50;">🟢 绿色</span>：当前PB已低于请客价（触发买入）</li>
                <li><span style="color: #FFC107;">🟡 黄色</span>：距离请客价10%以内</li>
                <li><span style="color: #FF9800;">🟠 橙色</span>：距离请客价20%以内</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown("""
        <div class="metric-card">
            <h4>⚠️ 风险提示</h4>
            <p style="color: #666; margin: 0.5rem 0;">
                智能选股基于历史PB数据分析，仅供参考。<br><br>
                投资决策请结合：
            </p>
            <ul style="color: #666; margin: 0; padding-left: 1.2rem;">
                <li>基本面分析</li>
                <li>行业前景研判</li>
                <li>个人风险承受能力</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

# Footer
st.markdown(render_footer(), unsafe_allow_html=True)

session.close()
