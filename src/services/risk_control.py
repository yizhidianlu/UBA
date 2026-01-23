"""Risk control module for position and compliance validation."""
from typing import Optional, Tuple
from dataclasses import dataclass
from sqlalchemy.orm import Session

from ..database.models import Asset, PortfolioPosition


@dataclass
class RiskCheckResult:
    """风控检查结果"""
    passed: bool
    current_position: float
    planned_position: float
    max_position: float
    violation_reason: Optional[str] = None
    warning: Optional[str] = None


class RiskControl:
    """风控模块：仓位限制、合规检查"""

    # 默认配置
    DEFAULT_MAX_SINGLE_POSITION = 10.0  # 单票最大仓位百分比
    DEFAULT_MAX_TOTAL_POSITION = 100.0  # 最大总仓位百分比

    def __init__(
        self,
        session: Session,
        user_id: int,
        max_single_position: float = DEFAULT_MAX_SINGLE_POSITION,
        max_total_position: float = DEFAULT_MAX_TOTAL_POSITION
    ):
        self.session = session
        self.user_id = user_id
        self.max_single_position = max_single_position
        self.max_total_position = max_total_position

    def check_buy_risk(
        self,
        asset_id: int,
        planned_position_pct: float
    ) -> RiskCheckResult:
        """
        检查买入风控
        - 单票仓位是否超过上限
        - 总仓位是否超过上限
        """
        # Get current position
        position = self.session.query(PortfolioPosition).filter(
            PortfolioPosition.asset_id == asset_id,
            PortfolioPosition.user_id == self.user_id
        ).first()

        current_position = position.position_pct if position else 0

        # Calculate new position after buy
        new_position = current_position + planned_position_pct

        # Check single stock limit
        if new_position > self.max_single_position:
            return RiskCheckResult(
                passed=False,
                current_position=current_position,
                planned_position=planned_position_pct,
                max_position=self.max_single_position,
                violation_reason=f"超出单票仓位上限：计划仓位 {new_position:.1f}% > 上限 {self.max_single_position:.1f}%"
            )

        # Check total position limit
        total_current = self._get_total_position()
        total_new = total_current - current_position + new_position

        if total_new > self.max_total_position:
            return RiskCheckResult(
                passed=False,
                current_position=current_position,
                planned_position=planned_position_pct,
                max_position=self.max_total_position,
                violation_reason=f"超出总仓位上限：总仓位将达到 {total_new:.1f}% > 上限 {self.max_total_position:.1f}%"
            )

        # Passed, but may have warning
        warning = None
        if new_position >= self.max_single_position * 0.8:
            warning = f"注意：买入后仓位将达到 {new_position:.1f}%，接近上限 {self.max_single_position:.1f}%"

        return RiskCheckResult(
            passed=True,
            current_position=current_position,
            planned_position=planned_position_pct,
            max_position=self.max_single_position,
            warning=warning
        )

    def check_add_risk(
        self,
        asset_id: int,
        additional_position_pct: float
    ) -> RiskCheckResult:
        """检查加仓风控"""
        return self.check_buy_risk(asset_id, additional_position_pct)

    def check_sell_risk(
        self,
        asset_id: int,
        sell_position_pct: float
    ) -> RiskCheckResult:
        """
        检查卖出风控
        - 卖出数量不能超过持仓
        """
        position = self.session.query(PortfolioPosition).filter(
            PortfolioPosition.asset_id == asset_id,
            PortfolioPosition.user_id == self.user_id
        ).first()

        current_position = position.position_pct if position else 0

        if sell_position_pct > current_position:
            return RiskCheckResult(
                passed=False,
                current_position=current_position,
                planned_position=sell_position_pct,
                max_position=current_position,
                violation_reason=f"卖出仓位 {sell_position_pct:.1f}% 超过当前持仓 {current_position:.1f}%"
            )

        return RiskCheckResult(
            passed=True,
            current_position=current_position,
            planned_position=sell_position_pct,
            max_position=current_position
        )

    def _get_total_position(self) -> float:
        """获取当前总仓位"""
        positions = self.session.query(PortfolioPosition).filter(
            PortfolioPosition.user_id == self.user_id
        ).all()
        return sum(p.position_pct for p in positions if p.position_pct)

    def get_position_summary(self) -> dict:
        """获取仓位汇总"""
        positions = self.session.query(PortfolioPosition).filter(
            PortfolioPosition.position_pct > 0,
            PortfolioPosition.user_id == self.user_id
        ).all()

        total_position = sum(p.position_pct for p in positions)
        cash_position = 100 - total_position

        return {
            'total_position_pct': total_position,
            'cash_position_pct': cash_position,
            'stock_count': len(positions),
            'max_single_position': self.max_single_position,
            'max_total_position': self.max_total_position,
            'positions': [
                {
                    'asset_id': p.asset_id,
                    'position_pct': p.position_pct,
                    'avg_cost': p.avg_cost
                }
                for p in positions
            ]
        }

    def get_available_position(self, asset_id: Optional[int] = None) -> float:
        """
        获取可用仓位空间
        如果指定asset_id，返回该股票还能买入的仓位
        否则返回总体可用仓位
        """
        total_current = self._get_total_position()

        if asset_id:
            position = self.session.query(PortfolioPosition).filter(
                PortfolioPosition.asset_id == asset_id,
                PortfolioPosition.user_id == self.user_id
            ).first()
            current_stock_position = position.position_pct if position else 0

            # Available is minimum of: single stock limit remaining, total limit remaining
            single_available = self.max_single_position - current_stock_position
            total_available = self.max_total_position - total_current

            return max(0, min(single_available, total_available))

        return max(0, self.max_total_position - total_current)

    def update_position(
        self,
        asset_id: int,
        new_position_pct: float,
        avg_cost: Optional[float] = None,
        shares: Optional[int] = None
    ) -> PortfolioPosition:
        """更新持仓"""
        position = self.session.query(PortfolioPosition).filter(
            PortfolioPosition.asset_id == asset_id,
            PortfolioPosition.user_id == self.user_id
        ).first()

        if position:
            position.position_pct = new_position_pct
            if avg_cost is not None:
                position.avg_cost = avg_cost
            if shares is not None:
                position.shares = shares
        else:
            position = PortfolioPosition(
                user_id=self.user_id,
                asset_id=asset_id,
                position_pct=new_position_pct,
                avg_cost=avg_cost,
                shares=shares or 0
            )
            self.session.add(position)

        self.session.commit()
        return position
