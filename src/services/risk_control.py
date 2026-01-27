"""Risk control module for position and compliance validation."""
from typing import Optional, Tuple, Dict
from dataclasses import dataclass
from datetime import date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database.models import Asset, PortfolioPosition, Portfolio, Action


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
    DEFAULT_MIN_CASH_RATIO = 5.0  # 最低现金比例
    DEFAULT_MAX_INDUSTRY_CONCENTRATION = 30.0  # 单行业最大集中度
    DEFAULT_MAX_DAILY_TURNOVER = 30.0  # 单日最大换手率

    def __init__(
        self,
        session: Session,
        user_id: int,
        max_single_position: float = DEFAULT_MAX_SINGLE_POSITION,
        max_total_position: float = DEFAULT_MAX_TOTAL_POSITION,
        min_cash_ratio: float = DEFAULT_MIN_CASH_RATIO,
        max_industry_concentration: float = DEFAULT_MAX_INDUSTRY_CONCENTRATION,
        max_daily_turnover: float = DEFAULT_MAX_DAILY_TURNOVER
    ):
        self.session = session
        self.user_id = user_id
        self.max_single_position = max_single_position
        self.max_total_position = max_total_position
        self.min_cash_ratio = min_cash_ratio
        self.max_industry_concentration = max_industry_concentration
        self.max_daily_turnover = max_daily_turnover

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

    def check_cash_sufficient(self, required_amount: float) -> Tuple[bool, Optional[str]]:
        """
        检查现金是否充足

        Args:
            required_amount: 需要的金额

        Returns:
            (是否充足, 错误信息)
        """
        portfolio = self.session.query(Portfolio).filter(
            Portfolio.user_id == self.user_id
        ).first()

        if not portfolio:
            return False, "未找到资金账户"

        available_cash = portfolio.available_cash

        if required_amount > available_cash:
            return False, f"现金不足：需要 {required_amount:.2f}，可用 {available_cash:.2f}"

        # 检查买入后是否会低于最低现金比例
        if portfolio.total_asset > 0:
            new_cash = available_cash - required_amount
            new_cash_ratio = (new_cash / portfolio.total_asset) * 100

            if new_cash_ratio < self.min_cash_ratio:
                return False, f"现金比例过低：操作后现金比例 {new_cash_ratio:.1f}% < 下限 {self.min_cash_ratio:.1f}%"

        return True, None

    def check_industry_concentration(self, asset_id: int, additional_pct: float) -> Tuple[bool, Optional[str]]:
        """
        检查行业集中度

        Args:
            asset_id: 股票ID
            additional_pct: 额外增加的仓位百分比

        Returns:
            (是否合规, 警告信息)
        """
        # 获取该股票的行业
        asset = self.session.query(Asset).filter(Asset.id == asset_id).first()
        if not asset or not asset.industry:
            return True, None  # 无行业信息，跳过检查

        # 获取同行业所有持仓
        industry_positions = self.session.query(
            PortfolioPosition, Asset
        ).join(
            Asset, PortfolioPosition.asset_id == Asset.id
        ).filter(
            PortfolioPosition.user_id == self.user_id,
            Asset.industry == asset.industry
        ).all()

        current_industry_pct = sum(p[0].position_pct for p in industry_positions if p[0].position_pct)
        new_industry_pct = current_industry_pct + additional_pct

        if new_industry_pct > self.max_industry_concentration:
            return False, f"行业集中度过高：{asset.industry} 行业仓位将达到 {new_industry_pct:.1f}% > 上限 {self.max_industry_concentration:.1f}%"

        if new_industry_pct > self.max_industry_concentration * 0.8:
            return True, f"警告：{asset.industry} 行业仓位将达到 {new_industry_pct:.1f}%，接近上限"

        return True, None

    def check_daily_turnover(self, trade_amount: float) -> Tuple[bool, Optional[str]]:
        """
        检查单日换手率

        Args:
            trade_amount: 本次交易金额

        Returns:
            (是否合规, 错误信息)
        """
        portfolio = self.session.query(Portfolio).filter(
            Portfolio.user_id == self.user_id
        ).first()

        if not portfolio or portfolio.total_asset == 0:
            return True, None

        # 获取今日已发生的交易金额
        today = date.today()
        today_actions = self.session.query(Action).filter(
            Action.user_id == self.user_id,
            Action.action_date == today
        ).all()

        today_total_amount = sum(
            a.executed_amount or 0 for a in today_actions
        )

        # 计算换手率
        new_turnover = ((today_total_amount + trade_amount) / portfolio.total_asset) * 100

        if new_turnover > self.max_daily_turnover:
            return False, f"单日换手率过高：{new_turnover:.1f}% > 上限 {self.max_daily_turnover:.1f}%"

        return True, None

    def get_industry_distribution(self) -> Dict[str, float]:
        """获取行业分布"""
        industry_positions = self.session.query(
            Asset.industry,
            func.sum(PortfolioPosition.position_pct).label('total_pct')
        ).join(
            PortfolioPosition, Asset.id == PortfolioPosition.asset_id
        ).filter(
            PortfolioPosition.user_id == self.user_id,
            PortfolioPosition.position_pct > 0
        ).group_by(
            Asset.industry
        ).all()

        return {
            industry or '未分类': total_pct
            for industry, total_pct in industry_positions
        }

    def comprehensive_check(
        self,
        asset_id: int,
        action_type: str,
        amount: float,
        position_pct: float
    ) -> RiskCheckResult:
        """
        综合风控检查

        Args:
            asset_id: 股票ID
            action_type: 操作类型 (BUY/ADD/SELL)
            amount: 交易金额
            position_pct: 仓位百分比

        Returns:
            风控检查结果
        """
        # 1. 检查仓位限制
        if action_type in ['BUY', 'ADD']:
            basic_check = self.check_buy_risk(asset_id, position_pct)
            if not basic_check.passed:
                return basic_check

            # 2. 检查现金是否充足
            cash_ok, cash_msg = self.check_cash_sufficient(amount)
            if not cash_ok:
                return RiskCheckResult(
                    passed=False,
                    current_position=basic_check.current_position,
                    planned_position=position_pct,
                    max_position=basic_check.max_position,
                    violation_reason=cash_msg
                )

            # 3. 检查行业集中度
            industry_ok, industry_msg = self.check_industry_concentration(asset_id, position_pct)
            if not industry_ok:
                return RiskCheckResult(
                    passed=False,
                    current_position=basic_check.current_position,
                    planned_position=position_pct,
                    max_position=basic_check.max_position,
                    violation_reason=industry_msg
                )

            # 4. 检查单日换手率
            turnover_ok, turnover_msg = self.check_daily_turnover(amount)
            if not turnover_ok:
                return RiskCheckResult(
                    passed=False,
                    current_position=basic_check.current_position,
                    planned_position=position_pct,
                    max_position=basic_check.max_position,
                    violation_reason=turnover_msg
                )

            # 合并警告信息
            warnings = []
            if basic_check.warning:
                warnings.append(basic_check.warning)
            if industry_msg:
                warnings.append(industry_msg)

            warning = '; '.join(warnings) if warnings else None

            return RiskCheckResult(
                passed=True,
                current_position=basic_check.current_position,
                planned_position=position_pct,
                max_position=basic_check.max_position,
                warning=warning
            )

        elif action_type == 'SELL':
            return self.check_sell_risk(asset_id, position_pct)

        return RiskCheckResult(
            passed=True,
            current_position=0,
            planned_position=position_pct,
            max_position=100
        )
