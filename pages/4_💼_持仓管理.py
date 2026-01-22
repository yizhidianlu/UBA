"""Portfolio management page."""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from src.database import get_session
from src.database.models import Asset, PortfolioPosition, Action
from src.services import RiskControl, ActionService

st.set_page_config(page_title="持仓管理 - 不败之地", page_icon="💼", layout="wide")
st.title("💼 持仓管理")

session = get_session()
risk_control = RiskControl(session)
action_service = ActionService(session)

# Position summary
summary = risk_control.get_position_summary()

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("总仓位", f"{summary['total_position_pct']:.1f}%")
with col2:
    st.metric("现金仓位", f"{summary['cash_position_pct']:.1f}%")
with col3:
    st.metric("持仓股票数", summary['stock_count'])
with col4:
    st.metric("单票上限", f"{summary['max_single_position']:.0f}%")

st.divider()

# Position table and chart
col_left, col_right = st.columns([1, 1])

with col_left:
    st.subheader("持仓明细")

    positions = session.query(PortfolioPosition).filter(
        PortfolioPosition.position_pct > 0
    ).all()

    if positions:
        data = []
        for pos in positions:
            asset = session.query(Asset).filter(Asset.id == pos.asset_id).first()
            if asset:
                data.append({
                    "股票": asset.name,
                    "代码": asset.code,
                    "仓位(%)": pos.position_pct,
                    "持股数": pos.shares or 0,
                    "成本": pos.avg_cost or 0,
                    "更新时间": pos.updated_at.strftime("%Y-%m-%d %H:%M") if pos.updated_at else "-"
                })

        df = pd.DataFrame(data)
        st.dataframe(
            df.style.format({
                "仓位(%)": "{:.1f}",
                "成本": "{:.2f}"
            }),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("暂无持仓")

with col_right:
    st.subheader("仓位分布")

    if positions:
        chart_data = []
        for pos in positions:
            asset = session.query(Asset).filter(Asset.id == pos.asset_id).first()
            if asset:
                chart_data.append({
                    "名称": asset.name,
                    "仓位": pos.position_pct
                })

        # Add cash
        cash_pct = 100 - sum(p.position_pct for p in positions)
        chart_data.append({"名称": "现金", "仓位": cash_pct})

        fig = px.pie(
            chart_data,
            values="仓位",
            names="名称",
            hole=0.4
        )
        fig.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig, use_container_width=True)
    else:
        # Show 100% cash
        fig = px.pie(
            [{"名称": "现金", "仓位": 100}],
            values="仓位",
            names="名称",
            hole=0.4
        )
        st.plotly_chart(fig, use_container_width=True)

st.divider()

# Recent actions
st.subheader("最近交易记录")

recent_actions = action_service.get_recent_actions(limit=20)

if recent_actions:
    action_data = []
    for action in recent_actions:
        asset = session.query(Asset).filter(Asset.id == action.asset_id).first()
        action_data.append({
            "日期": action.action_date,
            "股票": asset.name if asset else "-",
            "动作": action.action_type.value,
            "仓位变动(%)": action.executed_position_pct or 0,
            "价格": action.price or "-",
            "合规": "✅" if action.rule_compliance else "❌",
            "理由": action.reason[:30] + "..." if len(action.reason) > 30 else action.reason
        })

    df = pd.DataFrame(action_data)
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("暂无交易记录")

st.divider()

# Compliance stats
st.subheader("合规统计")

compliance = action_service.get_compliance_stats(days=90)

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("总交易次数", compliance['total_actions'])
with col2:
    st.metric("合规交易", compliance['compliant_actions'])
with col3:
    rate = compliance['compliance_rate']
    delta_color = "normal" if rate >= 90 else "inverse"
    st.metric("合规率", f"{rate:.1f}%")

if compliance['violations']:
    st.warning(f"近90天有 {len(compliance['violations'])} 次违规操作")

    with st.expander("查看违规详情"):
        for v in compliance['violations']:
            asset = session.query(Asset).filter(Asset.id == v['asset_id']).first()
            st.markdown(f"- **{v['date']}** {asset.name if asset else '-'} ({v['type']}): {v['note']}")

st.divider()

# Manual position adjustment
with st.expander("⚙️ 手动调整仓位"):
    st.warning("此功能用于修正数据，正常交易请通过信号中心执行")

    stocks = session.query(Asset).all()
    if stocks:
        selected_code = st.selectbox(
            "选择股票",
            options=[s.code for s in stocks],
            format_func=lambda x: f"{x} - {next((s.name for s in stocks if s.code == x), '')}"
        )

        if selected_code:
            asset = next((s for s in stocks if s.code == selected_code), None)
            if asset:
                pos = session.query(PortfolioPosition).filter(
                    PortfolioPosition.asset_id == asset.id
                ).first()

                current_pct = float(pos.position_pct) if pos and pos.position_pct else 0.0
                current_cost = float(pos.avg_cost) if pos and pos.avg_cost else 0.0

                col1, col2 = st.columns(2)
                with col1:
                    new_pct = st.number_input("仓位(%)", value=current_pct, min_value=0.0, max_value=100.0, step=0.1)
                with col2:
                    new_cost = st.number_input("平均成本", value=current_cost, min_value=0.0, step=0.01)

                if st.button("更新仓位"):
                    risk_control.update_position(
                        asset_id=asset.id,
                        new_position_pct=new_pct,
                        avg_cost=new_cost if new_cost > 0 else None
                    )
                    st.success("仓位已更新")
                    st.rerun()

session.close()
