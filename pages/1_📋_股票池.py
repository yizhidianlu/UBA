"""Stock pool management page with auto-analysis and real-time data."""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
from src.database import get_session
from src.database.models import Market, Valuation
from src.services import StockPoolService, ValuationService, StockAnalyzer, RealtimeService, AIAnalyzer
from src.ui import GLOBAL_CSS, APP_NAME_CN, APP_NAME_EN, render_header, render_footer

st.set_page_config(
    page_title=f"股票池 - {APP_NAME_CN} | {APP_NAME_EN}",
    page_icon="📋",
    layout="wide"
)

# Apply global styles
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

# Header
st.markdown(render_header("股票池管理", "添加、编辑和管理您的能力圈股票", "📋"), unsafe_allow_html=True)

col1, col2 = st.columns([4, 1])
with col2:
    if st.button("🔄 刷新", use_container_width=True):
        st.rerun()

# Initialize services
session = get_session()
stock_service = StockPoolService(session)
valuation_service = ValuationService(session)
realtime_service = RealtimeService()

@st.cache_resource
def get_analyzer():
    return StockAnalyzer()

analyzer = get_analyzer()

# Session state
if 'analysis_result' not in st.session_state:
    st.session_state.analysis_result = None
if 'search_results' not in st.session_state:
    st.session_state.search_results = None

# ==================== Add New Stock Section ====================
st.markdown("### ➕ 添加新股票")

tab_code, tab_name = st.tabs(["按代码添加", "按名称搜索"])

with tab_code:
    col1, col2 = st.columns([3, 1])

    with col1:
        input_code = st.text_input(
            "股票代码",
            placeholder="输入股票代码，如 600519 或 000858",
            help="支持格式：纯数字(600519)、带后缀(600519.SH)",
            key="code_input"
        )

    with col2:
        st.write("")
        st.write("")
        analyze_btn = st.button("🔍 分析股票", type="primary", use_container_width=True, key="analyze_code")

    if analyze_btn and input_code:
        with st.spinner("正在分析股票数据，请稍候..."):
            try:
                result = analyzer.full_analysis(input_code)
                st.session_state.analysis_result = result
            except Exception as e:
                st.error(f"分析失败: {e}")
                st.session_state.analysis_result = None

with tab_name:
    col1, col2 = st.columns([3, 1])

    with col1:
        search_name = st.text_input(
            "股票名称",
            placeholder="输入股票名称关键词，如 茅台、平安、招商",
            help="支持模糊搜索，输入部分名称即可",
            key="name_input"
        )

    with col2:
        st.write("")
        st.write("")
        search_btn = st.button("🔍 搜索股票", type="primary", use_container_width=True, key="search_name")

    if search_btn and search_name:
        with st.spinner("正在搜索..."):
            try:
                results = analyzer.search_stock_by_name(search_name, limit=10)
                st.session_state.search_results = results
            except Exception as e:
                st.error(f"搜索失败: {e}")
                st.session_state.search_results = None

    # Display search results
    if st.session_state.search_results:
        st.markdown("**搜索结果：**")
        for idx, stock in enumerate(st.session_state.search_results):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{stock.name}** ({stock.code})")
            with col2:
                if st.button(f"分析", key=f"analyze_search_{idx}", use_container_width=True):
                    with st.spinner(f"正在分析 {stock.name}..."):
                        try:
                            result = analyzer.full_analysis(stock.code)
                            st.session_state.analysis_result = result
                            st.session_state.search_results = None
                            st.rerun()
                        except Exception as e:
                            st.error(f"分析失败: {e}")

# Display analysis results
if st.session_state.analysis_result:
    result = st.session_state.analysis_result

    if result.get('error') and not result.get('stock_info'):
        st.error(result['error'])
    else:
        stock_info = result.get('stock_info')
        pb_analysis = result.get('pb_analysis')

        st.success(f"✅ 已识别: **{stock_info.name}** ({stock_info.code}) - {stock_info.industry or '未知行业'}")

        with st.expander("📊 PB 历史分析", expanded=True):
            if pb_analysis:
                col1, col2, col3, col4, col5 = st.columns(5)

                with col1:
                    current_display = f"{pb_analysis.current_pb:.2f}" if pb_analysis.current_pb else "N/A"
                    st.metric("当前 PB", current_display)
                with col2:
                    st.metric("最低 PB", f"{pb_analysis.min_pb:.2f}")
                with col3:
                    st.metric("最高 PB", f"{pb_analysis.max_pb:.2f}")
                with col4:
                    st.metric("平均 PB", f"{pb_analysis.avg_pb:.2f}")
                with col5:
                    st.metric("中位数", f"{pb_analysis.median_pb:.2f}")

                st.caption(f"📈 数据范围: 近 {pb_analysis.data_years} 年，共 {pb_analysis.data_count} 条数据")

                if pb_analysis.pb_history:
                    dates = [d[0] for d in pb_analysis.pb_history]
                    pbs = [d[1] for d in pb_analysis.pb_history]

                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=dates, y=pbs, mode='lines', name='PB',
                                            line=dict(color='#1E88E5', width=2)))
                    fig.add_hline(y=pb_analysis.recommended_buy_pb, line_dash="dash", line_color="#4CAF50",
                                  annotation_text=f"推荐请客价: {pb_analysis.recommended_buy_pb}")
                    fig.add_hline(y=pb_analysis.avg_pb, line_dash="dot", line_color="#9E9E9E",
                                  annotation_text=f"平均值: {pb_analysis.avg_pb}")
                    fig.update_layout(
                        title=dict(text=f"{stock_info.name} 历史 PB 走势", font=dict(size=16)),
                        xaxis_title="日期",
                        yaxis_title="PB",
                        height=350,
                        margin=dict(l=0, r=0, t=40, b=0),
                        plot_bgcolor='rgba(0,0,0,0)',
                        paper_bgcolor='rgba(0,0,0,0)'
                    )
                    st.plotly_chart(fig, use_container_width=True)

                st.info(f"""
                **💡 推荐阈值** (基于历史分位数)
                - 请客价 (25%分位): **{pb_analysis.recommended_buy_pb}**
                - 加仓价 (10%分位): **{pb_analysis.recommended_add_pb}**
                - 退出价 (75%分位): **{pb_analysis.recommended_sell_pb}**
                """)
            else:
                st.warning("⚠️ 无法获取PB历史数据，请手动填写阈值")

        st.divider()
        st.markdown("**📝 确认并添加到股票池**")

        with st.form("add_stock_form"):
            col1, col2 = st.columns(2)

            with col1:
                form_code = st.text_input("股票代码", value=stock_info.code, disabled=True)
                form_name = st.text_input("股票名称", value=stock_info.name)
                market_map = {"A股": Market.A_SHARE, "港股": Market.HK, "美股": Market.US}
                market_options = list(market_map.keys())
                default_market_idx = market_options.index(stock_info.market) if stock_info.market in market_options else 0
                form_market = st.selectbox("市场", options=market_options, index=default_market_idx)
                form_industry = st.text_input("行业", value=stock_info.industry or "")

            with col2:
                form_competence = st.slider("能力圈评分", 1, 5, 3)
                default_buy = pb_analysis.recommended_buy_pb if pb_analysis else 1.5
                default_add = pb_analysis.recommended_add_pb if pb_analysis else 0.0
                default_sell = pb_analysis.recommended_sell_pb if pb_analysis else 0.0

                form_buy_pb = st.number_input("请客价 (PB)", min_value=0.01, value=float(default_buy), step=0.1)
                form_add_pb = st.number_input("加仓价 (PB)", min_value=0.0, value=float(default_add), step=0.1)
                form_sell_pb = st.number_input("退出价 (PB)", min_value=0.0, value=float(default_sell), step=0.1)

            form_notes = st.text_area("投资备注", placeholder="护城河分析、投资要点等")

            submitted = st.form_submit_button("✅ 添加到股票池", type="primary", use_container_width=True)

            if submitted:
                try:
                    asset = stock_service.add_stock(
                        code=stock_info.code,
                        name=form_name,
                        market=market_map[form_market],
                        industry=form_industry if form_industry else None,
                        competence_score=form_competence,
                        notes=form_notes if form_notes else None,
                        buy_pb=form_buy_pb,
                        add_pb=form_add_pb if form_add_pb > 0 else None,
                        sell_pb=form_sell_pb if form_sell_pb > 0 else None
                    )

                    if pb_analysis and pb_analysis.pb_history:
                        for pb_date, pb_value in pb_analysis.pb_history:
                            try:
                                valuation_service.save_valuation(asset_id=asset.id, val_date=pb_date, pb=pb_value, data_source="analysis")
                            except Exception:
                                pass

                    st.success(f"✅ 成功添加: {form_name} ({stock_info.code})")
                    st.session_state.analysis_result = None
                    st.rerun()

                except ValueError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"添加失败: {e}")

st.divider()

# ==================== Stock List with Real-time Data ====================
st.markdown("### 📋 股票列表")

# Get stocks
stocks = stock_service.get_all_stocks()

if stocks:
    # Fetch real-time data
    stock_codes = [s.code for s in stocks]
    with st.spinner("获取实时数据..."):
        realtime_data = realtime_service.get_batch_quotes(stock_codes)

    st.caption(f"📡 实时数据更新于: {datetime.now().strftime('%H:%M:%S')}")

    # Build table data
    data = []
    for stock in stocks:
        quote = realtime_data.get(stock.code)
        current_pb = quote.pb if quote else None
        current_price = quote.price if quote else None
        change_pct = quote.change_pct if quote else 0

        threshold = stock.threshold
        buy_pb = threshold.buy_pb if threshold else None

        # Status
        if current_pb and buy_pb:
            if current_pb <= buy_pb:
                status = "🟢 触发"
            elif threshold.sell_pb and current_pb >= threshold.sell_pb:
                status = "🔴 高估"
            else:
                status = "⚪ 监控"
        else:
            status = "❓"

        # Distance
        if current_pb and buy_pb:
            distance = ((current_pb - buy_pb) / buy_pb) * 100
            distance_str = f"{distance:+.1f}%"
        else:
            distance_str = "-"

        data.append({
            "状态": status,
            "代码": stock.code,
            "名称": stock.name,
            "行业": stock.industry or "-",
            "现价": f"{current_price:.2f}" if current_price else "-",
            "涨跌": f"{change_pct:+.2f}%" if change_pct else "-",
            "实时PB": f"{current_pb:.2f}" if current_pb else "-",
            "请客价": f"{buy_pb:.2f}" if buy_pb else "-",
            "距离": distance_str,
            "能力圈": "⭐" * stock.competence_score,
            "AI评分": "🤖" + "⭐" * stock.ai_score if stock.ai_score else "-"
        })

    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True, hide_index=True, height=400)

    # Edit section
    st.divider()
    st.markdown("### ✏️ 编辑股票")

    selected_code = st.selectbox(
        "选择股票",
        [s.code for s in stocks],
        format_func=lambda x: f"{x} - {next((s.name for s in stocks if s.code == x), '')}"
    )

    if selected_code:
        stock = stock_service.get_stock(selected_code)
        if stock:
            quote = realtime_data.get(stock.code)

            col1, col2 = st.columns(2)

            with col1:
                st.markdown(f"#### {stock.name}")
                st.markdown(f"**代码:** {stock.code} | **市场:** {stock.market.value}")
                st.markdown(f"**行业:** {stock.industry or '未设置'}")

                if quote:
                    st.markdown(f"**实时数据:** 价格 {quote.price:.2f} | PB {quote.pb:.2f}" if quote.pb else f"**实时价格:** {quote.price:.2f}")

                # 评分编辑
                st.markdown("**评分设置**")
                new_competence = st.slider(
                    "能力圈评分",
                    min_value=1,
                    max_value=5,
                    value=stock.competence_score,
                    help="您对该股票的理解程度 (1-5)",
                    key="edit_competence"
                )

                ai_score_display = f"🤖 {'⭐' * stock.ai_score} ({stock.ai_score}分)" if stock.ai_score else "未评分"
                st.markdown(f"**AI评分:** {ai_score_display}")
                if stock.ai_suggestion:
                    st.caption(f"AI建议: {stock.ai_suggestion[:100]}..." if len(stock.ai_suggestion or '') > 100 else f"AI建议: {stock.ai_suggestion}")

                if st.button("💾 保存评分", use_container_width=True, key="save_score"):
                    stock_service.update_stock(stock.code, competence_score=new_competence)
                    st.success("评分已保存")
                    st.rerun()

            with col2:
                st.markdown("**阈值设置**")

                if stock.threshold:
                    stats = valuation_service.get_pb_stats(stock.id, years=5)
                    if stats:
                        st.caption(f"历史参考: 最低 {stats['min_pb']:.2f} / 平均 {stats['avg_pb']:.2f} / 最高 {stats['max_pb']:.2f}")

                    new_buy_pb = st.number_input("请客价", value=float(stock.threshold.buy_pb), min_value=0.01, step=0.01, key="edit_buy")
                    new_add_pb = st.number_input("加仓价", value=float(stock.threshold.add_pb or 0.0), min_value=0.0, step=0.01, key="edit_add")
                    new_sell_pb = st.number_input("退出价", value=float(stock.threshold.sell_pb or 0.0), min_value=0.0, step=0.01, key="edit_sell")

                    if st.button("💾 保存阈值", use_container_width=True):
                        stock_service.update_threshold(stock.code, buy_pb=new_buy_pb,
                                                       add_pb=new_add_pb if new_add_pb > 0 else None,
                                                       sell_pb=new_sell_pb if new_sell_pb > 0 else None)
                        st.success("已保存")
                        st.rerun()

            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("🔄 更新历史PB", use_container_width=True):
                    with st.spinner("获取数据..."):
                        pb_data = analyzer.fetch_pb_history(stock.code, years=5)
                        if pb_data:
                            for d in pb_data:
                                if d.get('pb'):
                                    valuation_service.save_valuation(asset_id=stock.id, val_date=d['date'], pb=d['pb'], data_source="update")
                            st.success(f"已更新 {len(pb_data)} 条数据")
                        else:
                            st.warning("未获取到数据")

            with col2:
                if st.button("🤖 更新AI评分", use_container_width=True):
                    with st.spinner("AI分析中..."):
                        try:
                            ai_analyzer = AIAnalyzer()
                            if ai_analyzer.last_error:
                                st.error(ai_analyzer.last_error)
                            else:
                                fundamental = ai_analyzer.fetch_fundamental_data(stock.code)
                                if fundamental:
                                    pb_data = analyzer.fetch_pb_history(stock.code, years=5)
                                    report = ai_analyzer.generate_analysis_report(
                                        fundamental,
                                        pb_history=pb_data,
                                        threshold_buy=stock.threshold.buy_pb if stock.threshold else None
                                    )
                                    if report:
                                        stock_service.update_stock(
                                            stock.code,
                                            ai_score=report.ai_score,
                                            ai_suggestion=report.summary
                                        )
                                        st.success(f"AI评分已更新: {report.ai_score}分")
                                        st.rerun()
                                    else:
                                        st.error(ai_analyzer.last_error or "AI分析失败")
                                else:
                                    st.error("无法获取股票数据")
                        except Exception as e:
                            st.error(f"AI分析失败: {e}")

            with col3:
                if st.button("🗑️ 删除股票", type="secondary", use_container_width=True):
                    stock_service.remove_stock(selected_code)
                    st.success(f"已删除 {selected_code}")
                    st.rerun()
else:
    st.info("股票池为空，请在上方添加股票")

# Footer
st.markdown(render_footer(), unsafe_allow_html=True)

session.close()
