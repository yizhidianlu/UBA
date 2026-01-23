"""Stock detail page with PB history chart."""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta
from src.database import get_session
from src.database.models import Asset, Signal, Action
from src.services import StockPoolService, ValuationService

st.set_page_config(page_title="股票详情 - 不败之地", page_icon="📈", layout="wide")
st.title("📈 股票详情")

session = get_session()
stock_service = StockPoolService(session)
valuation_service = ValuationService(session)

# Stock selector
stocks = stock_service.get_all_stocks()

if not stocks:
    st.info("股票池为空，请先添加股票")
    st.stop()

selected_code = st.selectbox(
    "选择股票",
    options=[s.code for s in stocks],
    format_func=lambda x: f"{x} - {next((s.name for s in stocks if s.code == x), '')}"
)

if selected_code:
    asset = stock_service.get_stock(selected_code)

    if asset:
        # Header info
        col1, col2, col3 = st.columns([2, 1, 1])

        with col1:
            st.header(f"{asset.name} ({asset.code})")
            st.markdown(f"**市场:** {asset.market.value} | **行业:** {asset.industry or '未设置'}")
            st.markdown(f"**关注指数评分:** {'⭐' * asset.competence_score}")

        with col2:
            if asset.threshold:
                st.metric("请客价 (PB)", f"{asset.threshold.buy_pb:.2f}")
            else:
                st.metric("请客价 (PB)", "未设置")

        with col3:
            latest = valuation_service.get_latest_pb(asset.id)
            if latest:
                st.metric("当前 PB", f"{latest.pb:.2f}", help=f"数据日期: {latest.date}")
            else:
                st.metric("当前 PB", "无数据")

        st.divider()

        # Tabs
        tab1, tab2, tab3, tab4 = st.tabs(["PB走势", "估值统计", "信号历史", "交易记录"])

        with tab1:
            # PB history chart
            st.subheader("PB 历史走势")

            # Time range selector
            time_range = st.radio(
                "时间范围",
                options=["1年", "3年", "5年", "全部"],
                horizontal=True
            )

            if time_range == "1年":
                start_date = date.today() - timedelta(days=365)
            elif time_range == "3年":
                start_date = date.today() - timedelta(days=365 * 3)
            elif time_range == "5年":
                start_date = date.today() - timedelta(days=365 * 5)
            else:
                start_date = None

            valuations = valuation_service.get_pb_history(asset.id, start_date=start_date)

            if valuations:
                # Create chart
                dates = [v.date for v in valuations]
                pbs = [v.pb for v in valuations]

                fig = go.Figure()

                # PB line
                fig.add_trace(go.Scatter(
                    x=dates,
                    y=pbs,
                    mode='lines',
                    name='PB',
                    line=dict(color='#1f77b4', width=2)
                ))

                # Threshold lines
                if asset.threshold:
                    fig.add_hline(
                        y=asset.threshold.buy_pb,
                        line_dash="dash",
                        line_color="green",
                        annotation_text=f"请客价: {asset.threshold.buy_pb:.2f}"
                    )

                    if asset.threshold.add_pb:
                        fig.add_hline(
                            y=asset.threshold.add_pb,
                            line_dash="dash",
                            line_color="blue",
                            annotation_text=f"加仓价: {asset.threshold.add_pb:.2f}"
                        )

                    if asset.threshold.sell_pb:
                        fig.add_hline(
                            y=asset.threshold.sell_pb,
                            line_dash="dash",
                            line_color="red",
                            annotation_text=f"退出价: {asset.threshold.sell_pb:.2f}"
                        )

                fig.update_layout(
                    title=f"{asset.name} PB 走势",
                    xaxis_title="日期",
                    yaxis_title="PB",
                    hovermode="x unified"
                )

                st.plotly_chart(fig, use_container_width=True)

                # Data table
                with st.expander("查看数据"):
                    df = pd.DataFrame({
                        "日期": dates,
                        "PB": pbs,
                        "价格": [v.price for v in valuations]
                    })
                    st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("暂无PB历史数据")

                if st.button("📥 获取历史数据"):
                    with st.spinner("正在获取数据..."):
                        try:
                            data_list = valuation_service.fetch_pb_data(asset.code)
                            if data_list:
                                count = valuation_service.batch_save_valuations(asset.id, data_list)
                                st.success(f"成功获取 {count} 条数据")
                                st.rerun()
                            else:
                                st.warning("未能获取数据，请检查股票代码或稍后重试")
                        except Exception as e:
                            st.error(f"获取数据失败: {e}")

        with tab2:
            st.subheader("估值统计")

            latest = valuation_service.get_latest_pb(asset.id)

            if latest:
                current_pb = latest.pb

                # Stats for different periods
                for years in [3, 5, 10]:
                    stats = valuation_service.get_pb_stats(asset.id, years=years)
                    if stats and stats['count'] > 0:
                        percentile = valuation_service.calculate_pb_percentile(
                            asset.id, current_pb, years=years
                        )

                        st.markdown(f"**近 {years} 年统计** (共 {stats['count']} 条数据)")

                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("最低 PB", f"{stats['min_pb']:.2f}")
                        with col2:
                            st.metric("最高 PB", f"{stats['max_pb']:.2f}")
                        with col3:
                            st.metric("平均 PB", f"{stats['avg_pb']:.2f}")
                        with col4:
                            if percentile is not None:
                                color = "🟢" if percentile <= 30 else ("🔴" if percentile >= 70 else "🟡")
                                st.metric("当前分位", f"{color} {percentile:.1f}%")

                        st.divider()
            else:
                st.info("暂无估值数据")

        with tab3:
            st.subheader("信号历史")

            signals = session.query(Signal).filter(
                Signal.asset_id == asset.id
            ).order_by(Signal.date.desc()).limit(50).all()

            if signals:
                data = []
                for s in signals:
                    status_emoji = {"OPEN": "🟢", "DONE": "✅", "IGNORED": "⏭️"}.get(s.status.value, "")
                    data.append({
                        "日期": s.date,
                        "类型": s.signal_type.value,
                        "PB": f"{s.pb:.2f}",
                        "阈值": f"{s.triggered_threshold:.2f}",
                        "状态": f"{status_emoji} {s.status.value}",
                        "解释": s.explanation[:50] + "..." if s.explanation and len(s.explanation) > 50 else s.explanation
                    })

                df = pd.DataFrame(data)
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("暂无信号历史")

        with tab4:
            st.subheader("交易记录")

            actions = session.query(Action).filter(
                Action.asset_id == asset.id
            ).order_by(Action.action_date.desc()).limit(50).all()

            if actions:
                data = []
                for a in actions:
                    compliance_emoji = "✅" if a.rule_compliance else "❌"
                    data.append({
                        "日期": a.action_date,
                        "动作": a.action_type.value,
                        "仓位变动": f"{a.executed_position_pct:.1f}%" if a.executed_position_pct else "-",
                        "价格": f"{a.price:.2f}" if a.price else "-",
                        "合规": compliance_emoji,
                        "理由": a.reason[:40] + "..." if len(a.reason) > 40 else a.reason
                    })

                df = pd.DataFrame(data)
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("暂无交易记录")

        # Notes section
        st.divider()
        st.subheader("投资备注")

        if asset.notes:
            st.markdown(asset.notes)
        else:
            st.info("暂无备注")

        with st.expander("编辑备注"):
            new_notes = st.text_area("备注内容", value=asset.notes or "", height=150)
            if st.button("保存备注"):
                stock_service.update_stock(asset.code, notes=new_notes)
                st.success("备注已保存")
                st.rerun()

session.close()
