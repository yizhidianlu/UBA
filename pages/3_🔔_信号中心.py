"""Signal center page for handling triggered signals."""
import streamlit as st
import pandas as pd
from datetime import date
from src.database import get_session, init_db
from src.database.models import Asset, Signal, SignalStatus, ActionType
from src.services import SignalEngine, ActionService, RiskControl
from src.ui import require_auth, render_auth_sidebar, get_current_user_id

st.set_page_config(page_title="信号中心 - 不败之地", page_icon="🔔", layout="wide")
st.title("🔔 信号中心")

init_db()
session = get_session()
require_auth(session)
user_id = get_current_user_id()
with st.sidebar:
    render_auth_sidebar()
    st.divider()
signal_engine = SignalEngine(session, user_id)
action_service = ActionService(session, user_id)
risk_control = RiskControl(session, user_id)

# Tabs for different signal views
tab1, tab2, tab3 = st.tabs(["待处理", "已处理", "已忽略"])

with tab1:
    open_signals = signal_engine.get_signals_by_status(SignalStatus.OPEN)

    # 过滤：只显示关注指数评分 >= 4 的股票
    filtered_signals = []
    for signal in open_signals:
        asset = session.query(Asset).filter(
            Asset.id == signal.asset_id,
            Asset.user_id == user_id
        ).first()
        if asset and asset.competence_score and asset.competence_score >= 4:
            filtered_signals.append((signal, asset))

    if filtered_signals:
        # 显示过滤提示
        if len(filtered_signals) < len(open_signals):
            st.caption(f"💡 仅显示关注指数评分 ≥ 4⭐ 的股票信号 ({len(filtered_signals)}/{len(open_signals)})")

        for signal, asset in filtered_signals:
            with st.expander(f"🔔 {asset.name} ({asset.code}) - {signal.signal_type.value} | 关注指数: {'⭐' * asset.competence_score}", expanded=True):
                # Signal info
                col1, col2 = st.columns([2, 1])

                with col1:
                    st.markdown(f"**信号类型:** {signal.signal_type.value}")
                    st.markdown(f"**触发日期:** {signal.date}")
                    st.markdown(f"**当前 PB:** {signal.pb:.2f}")
                    st.markdown(f"**触发阈值:** {signal.triggered_threshold:.2f}")
                    st.markdown(f"**解释:** {signal.explanation}")

                with col2:
                    # Risk info
                    available = risk_control.get_available_position(asset.id)
                    st.metric("可用仓位", f"{available:.1f}%")

                st.divider()

                # Action form
                st.markdown("**执行动作**")

                action_type = st.radio(
                    "选择动作",
                    options=["BUY", "ADD", "HOLD", "SELL"],
                    horizontal=True,
                    key=f"action_{signal.id}"
                )

                col1, col2 = st.columns(2)

                with col1:
                    if action_type in ["BUY", "ADD"]:
                        position_pct = st.number_input(
                            "买入仓位 (%)",
                            min_value=0.0,
                            max_value=10.0,
                            value=float(min(5.0, available)),
                            step=0.5,
                            key=f"position_{signal.id}"
                        )
                    elif action_type == "SELL":
                        # Get current position
                        from src.database.models import PortfolioPosition
                        pos = session.query(PortfolioPosition).filter(
                            PortfolioPosition.asset_id == asset.id
                        ).first()
                        current_pos = float(pos.position_pct) if pos and pos.position_pct else 0.0

                        position_pct = st.number_input(
                            "卖出仓位 (%)",
                            min_value=0.0,
                            max_value=max(0.01, current_pos),
                            value=current_pos,
                            step=0.5,
                            key=f"position_{signal.id}"
                        )
                    else:
                        position_pct = 0

                    price = st.number_input(
                        "成交价格 (可选)",
                        min_value=0.0,
                        value=0.0,
                        step=0.01,
                        key=f"price_{signal.id}"
                    )

                with col2:
                    emotion = st.selectbox(
                        "当前情绪 (可选)",
                        options=["", "理性", "恐惧", "贪婪", "犹豫", "兴奋", "焦虑"],
                        key=f"emotion_{signal.id}"
                    )

                reason = st.text_area(
                    "交易理由 (必填)",
                    placeholder="请说明为什么执行此动作，至少5个字符",
                    key=f"reason_{signal.id}"
                )

                # Cost inputs
                with st.expander("交易成本 (可选)"):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        fee = st.number_input("手续费", min_value=0.0, value=0.0, key=f"fee_{signal.id}")
                    with col2:
                        tax = st.number_input("印花税", min_value=0.0, value=0.0, key=f"tax_{signal.id}")
                    with col3:
                        slippage = st.number_input("滑点", min_value=0.0, value=0.0, key=f"slippage_{signal.id}")

                # Force execute option
                force_execute = st.checkbox("强制执行 (如果超出仓位限制)", key=f"force_{signal.id}")
                force_reason = ""
                if force_execute:
                    force_reason = st.text_input("强制执行原因", key=f"force_reason_{signal.id}")

                # Action buttons
                col1, col2 = st.columns(2)

                with col1:
                    if st.button("✅ 执行动作", key=f"execute_{signal.id}", type="primary"):
                        if not reason or len(reason.strip()) < 5:
                            st.error("请填写交易理由（至少5个字符）")
                        else:
                            try:
                                action_enum = ActionType[action_type]
                                action, message = action_service.execute_action(
                                    asset_id=asset.id,
                                    action_type=action_enum,
                                    planned_position_pct=position_pct,
                                    reason=reason,
                                    signal_id=signal.id,
                                    price=price if price > 0 else None,
                                    emotion=emotion if emotion else None,
                                    force_execute=force_execute,
                                    force_reason=force_reason if force_execute else None,
                                    fee=fee,
                                    tax=tax,
                                    slippage=slippage
                                )
                                st.success(message)
                                st.rerun()
                            except ValueError as e:
                                st.error(str(e))
                            except Exception as e:
                                st.error(f"执行失败: {e}")

                with col2:
                    if st.button("⏭️ 忽略信号", key=f"ignore_{signal.id}"):
                        if not reason or len(reason.strip()) < 5:
                            st.error("请填写忽略原因（至少5个字符）")
                        else:
                            try:
                                action_service.ignore_signal(signal.id, reason)
                                st.success("信号已忽略")
                                st.rerun()
                            except Exception as e:
                                st.error(f"操作失败: {e}")
    else:
        if open_signals:
            st.info(f"有 {len(open_signals)} 个信号，但均为关注指数评分 < 4⭐ 的股票，已过滤")
        else:
            st.info("暂无待处理信号")

        if st.button("🔄 扫描新信号"):
            with st.spinner("正在扫描..."):
                new_signals = signal_engine.scan_all_stocks()
                if new_signals:
                    # 统计高评分信号数量
                    high_score_count = 0
                    for sig in new_signals:
                        a = session.query(Asset).filter(
                            Asset.id == sig.asset_id,
                            Asset.user_id == user_id
                        ).first()
                        if a and a.competence_score and a.competence_score >= 4:
                            high_score_count += 1
                    st.success(f"发现 {len(new_signals)} 个新信号，其中 {high_score_count} 个来自高评分股票!")
                    st.rerun()
                else:
                    st.info("未发现新信号")

with tab2:
    done_signals = signal_engine.get_signals_by_status(SignalStatus.DONE)

    if done_signals:
        data = []
        for signal in done_signals:
            asset = session.query(Asset).filter(
                Asset.id == signal.asset_id,
                Asset.user_id == user_id
            ).first()
            data.append({
                "日期": signal.date,
                "股票": asset.name if asset else "-",
                "代码": asset.code if asset else "-",
                "类型": signal.signal_type.value,
                "PB": f"{signal.pb:.2f}",
                "阈值": f"{signal.triggered_threshold:.2f}"
            })

        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("暂无已处理信号")

with tab3:
    ignored_signals = signal_engine.get_signals_by_status(SignalStatus.IGNORED)

    if ignored_signals:
        data = []
        for signal in ignored_signals:
            asset = session.query(Asset).filter(
                Asset.id == signal.asset_id,
                Asset.user_id == user_id
            ).first()
            data.append({
                "日期": signal.date,
                "股票": asset.name if asset else "-",
                "代码": asset.code if asset else "-",
                "类型": signal.signal_type.value,
                "PB": f"{signal.pb:.2f}",
                "阈值": f"{signal.triggered_threshold:.2f}"
            })

        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("暂无已忽略信号")

session.close()
