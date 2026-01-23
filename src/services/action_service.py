"""Action service for trade execution logging."""
from typing import List, Optional, Tuple
from datetime import date, datetime
from sqlalchemy.orm import Session

from ..database.models import (
    Asset, Action, ActionType, Signal, SignalStatus,
    PortfolioPosition, Cost
)
from .risk_control import RiskControl


class ActionService:
    """四动作执行与记录服务"""

    def __init__(self, session: Session, user_id: int):
        self.session = session
        self.user_id = user_id
        self.risk_control = RiskControl(session, user_id)

    def execute_action(
        self,
        asset_id: int,
        action_type: ActionType,
        planned_position_pct: float,
        reason: str,
        signal_id: Optional[int] = None,
        price: Optional[float] = None,
        shares: Optional[int] = None,
        emotion: Optional[str] = None,
        force_execute: bool = False,
        force_reason: Optional[str] = None,
        fee: float = 0,
        tax: float = 0,
        slippage: float = 0
    ) -> Tuple[Action, str]:
        """
        执行交易动作
        返回: (Action对象, 提示信息)
        """
        # Validate reason
        if not reason or len(reason.strip()) < 5:
            raise ValueError("必须填写交易理由（至少5个字符）")

        # Risk check based on action type
        compliance = True
        compliance_note = None

        if action_type in [ActionType.BUY, ActionType.ADD]:
            risk_result = self.risk_control.check_buy_risk(asset_id, planned_position_pct)

            if not risk_result.passed:
                if not force_execute:
                    raise ValueError(f"风控检查不通过：{risk_result.violation_reason}")
                else:
                    if not force_reason:
                        raise ValueError("强制执行必须提供原因")
                    compliance = False
                    compliance_note = f"强制执行：{risk_result.violation_reason}。原因：{force_reason}"

            executed_position_pct = planned_position_pct

        elif action_type == ActionType.SELL:
            risk_result = self.risk_control.check_sell_risk(asset_id, planned_position_pct)

            if not risk_result.passed:
                raise ValueError(f"卖出检查不通过：{risk_result.violation_reason}")

            executed_position_pct = planned_position_pct

        else:  # HOLD
            executed_position_pct = 0

        # Create action record
        action = Action(
            user_id=self.user_id,
            asset_id=asset_id,
            signal_id=signal_id,
            action_date=date.today(),
            action_type=action_type,
            planned_position_pct=planned_position_pct,
            executed_position_pct=executed_position_pct,
            shares=shares,
            price=price,
            reason=reason,
            emotion=emotion,
            rule_compliance=compliance,
            compliance_note=compliance_note
        )
        self.session.add(action)
        self.session.flush()

        # Add costs if any
        if fee > 0 or tax > 0 or slippage > 0:
            cost = Cost(
                action_id=action.id,
                fee=fee,
                tax=tax,
                slippage=slippage
            )
            self.session.add(cost)

        # Update position
        if action_type in [ActionType.BUY, ActionType.ADD]:
            self._update_position_after_buy(asset_id, executed_position_pct, price)
        elif action_type == ActionType.SELL:
            self._update_position_after_sell(asset_id, executed_position_pct)

        # Update signal status if linked
        if signal_id:
            signal = self.session.query(Signal).filter(
                Signal.id == signal_id,
                Signal.user_id == self.user_id
            ).first()
            if signal:
                signal.status = SignalStatus.DONE

        self.session.commit()

        # Generate message
        message = self._generate_action_message(action, risk_result if action_type != ActionType.HOLD else None)

        return action, message

    def _update_position_after_buy(
        self,
        asset_id: int,
        position_change: float,
        price: Optional[float]
    ):
        """买入后更新持仓"""
        position = self.session.query(PortfolioPosition).filter(
            PortfolioPosition.asset_id == asset_id,
            PortfolioPosition.user_id == self.user_id
        ).first()

        if position:
            old_pct = position.position_pct
            new_pct = old_pct + position_change

            # Calculate new average cost if price provided
            if price and position.avg_cost:
                # Weighted average
                total_old = old_pct * position.avg_cost
                total_new = position_change * price
                position.avg_cost = (total_old + total_new) / new_pct if new_pct > 0 else price
            elif price:
                position.avg_cost = price

            position.position_pct = new_pct
        else:
            position = PortfolioPosition(
                user_id=self.user_id,
                asset_id=asset_id,
                position_pct=position_change,
                avg_cost=price
            )
            self.session.add(position)

    def _update_position_after_sell(self, asset_id: int, position_change: float):
        """卖出后更新持仓"""
        position = self.session.query(PortfolioPosition).filter(
            PortfolioPosition.asset_id == asset_id,
            PortfolioPosition.user_id == self.user_id
        ).first()

        if position:
            position.position_pct = max(0, position.position_pct - position_change)

    def _generate_action_message(self, action: Action, risk_result=None) -> str:
        """生成动作执行消息"""
        asset = self.session.query(Asset).filter(
            Asset.id == action.asset_id,
            Asset.user_id == self.user_id
        ).first()
        stock_name = asset.name if asset else f"股票ID:{action.asset_id}"

        messages = [f"已记录 {stock_name} 的 {action.action_type.value} 动作"]

        if action.executed_position_pct:
            messages.append(f"仓位变动: {action.executed_position_pct:.1f}%")

        if action.price:
            messages.append(f"成交价: {action.price:.2f}")

        if not action.rule_compliance:
            messages.append(f"[违规] {action.compliance_note}")
        elif risk_result and risk_result.warning:
            messages.append(f"[提示] {risk_result.warning}")

        return " | ".join(messages)

    def ignore_signal(self, signal_id: int, reason: str) -> Signal:
        """忽略信号（不执行任何动作）"""
        signal = self.session.query(Signal).filter(
            Signal.id == signal_id,
            Signal.user_id == self.user_id
        ).first()
        if not signal:
            raise ValueError(f"信号不存在: {signal_id}")

        # Create a HOLD action to record the decision
        action = Action(
            user_id=self.user_id,
            asset_id=signal.asset_id,
            signal_id=signal_id,
            action_date=date.today(),
            action_type=ActionType.HOLD,
            planned_position_pct=0,
            executed_position_pct=0,
            reason=reason,
            rule_compliance=True
        )
        self.session.add(action)

        signal.status = SignalStatus.IGNORED
        self.session.commit()

        return signal

    def get_action_history(
        self,
        asset_id: Optional[int] = None,
        action_type: Optional[ActionType] = None,
        days: int = 90
    ) -> List[Action]:
        """获取动作历史"""
        from datetime import timedelta
        start_date = date.today() - timedelta(days=days)

        query = self.session.query(Action).filter(
            Action.action_date >= start_date,
            Action.user_id == self.user_id
        )

        if asset_id:
            query = query.filter(Action.asset_id == asset_id)
        if action_type:
            query = query.filter(Action.action_type == action_type)

        return query.order_by(Action.action_date.desc()).all()

    def get_compliance_stats(self, days: int = 90) -> dict:
        """获取合规统计"""
        from datetime import timedelta
        start_date = date.today() - timedelta(days=days)

        actions = self.session.query(Action).filter(
            Action.action_date >= start_date,
            Action.action_type != ActionType.HOLD,
            Action.user_id == self.user_id
        ).all()

        if not actions:
            return {
                'total_actions': 0,
                'compliant_actions': 0,
                'compliance_rate': 100.0,
                'violations': []
            }

        compliant = [a for a in actions if a.rule_compliance]
        violations = [a for a in actions if not a.rule_compliance]

        return {
            'total_actions': len(actions),
            'compliant_actions': len(compliant),
            'compliance_rate': (len(compliant) / len(actions)) * 100,
            'violations': [
                {
                    'action_id': a.id,
                    'asset_id': a.asset_id,
                    'date': a.action_date,
                    'type': a.action_type.value,
                    'note': a.compliance_note
                }
                for a in violations
            ]
        }

    def get_recent_actions(self, limit: int = 10) -> List[Action]:
        """获取最近的动作"""
        return self.session.query(Action).filter(
            Action.user_id == self.user_id
        ).order_by(Action.created_at.desc()).limit(limit).all()
