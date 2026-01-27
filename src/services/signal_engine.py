"""Signal engine for PB trigger detection."""
from typing import List, Optional, Dict
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session

from ..database.models import Asset, Signal, SignalType, SignalStatus, Valuation
from .valuation import ValuationService


class SignalEngine:
    """信号引擎：检测PB触发并生成信号"""

    # 默认配置
    DEFAULT_MIN_ROE = 5.0  # 最低ROE要求（%）
    DEFAULT_SIGNAL_COOLDOWN_DAYS = 7  # 信号冷却期（天）
    DEFAULT_ENABLE_ROE_FILTER = True  # 是否启用ROE过滤
    DEFAULT_ENABLE_COOLDOWN = True  # 是否启用冷却期

    def __init__(
        self,
        session: Session,
        user_id: int,
        min_roe: float = DEFAULT_MIN_ROE,
        signal_cooldown_days: int = DEFAULT_SIGNAL_COOLDOWN_DAYS,
        enable_roe_filter: bool = DEFAULT_ENABLE_ROE_FILTER,
        enable_cooldown: bool = DEFAULT_ENABLE_COOLDOWN
    ):
        self.session = session
        self.user_id = user_id
        self.valuation_service = ValuationService(session)
        self.min_roe = min_roe
        self.signal_cooldown_days = signal_cooldown_days
        self.enable_roe_filter = enable_roe_filter
        self.enable_cooldown = enable_cooldown

    def check_triggers(self, asset: Asset) -> Optional[Signal]:
        """
        检查单只股票是否触发信号
        返回触发的信号（如有）
        """
        if not asset.threshold:
            return None

        # Get latest valuation
        latest = self.valuation_service.get_latest_pb(asset.id)
        if not latest or latest.pb is None:
            return None

        current_pb = latest.pb
        threshold = asset.threshold
        today = date.today()

        # Check if there's already an open signal for today
        existing = self.session.query(Signal).filter(
            Signal.asset_id == asset.id,
            Signal.user_id == self.user_id,
            Signal.date == today,
            Signal.status == SignalStatus.OPEN
        ).first()

        if existing:
            return existing

        signal_type = None
        triggered_threshold = None
        explanation = None

        # Get position to determine if ADD is applicable
        has_position = asset.position is not None and asset.position.position_pct > 0

        # Check SELL trigger first (highest priority if holding)
        if has_position and threshold.sell_pb and current_pb >= threshold.sell_pb:
            signal_type = SignalType.SELL
            triggered_threshold = threshold.sell_pb
            explanation = self._generate_explanation(
                asset, current_pb, threshold.sell_pb, "SELL"
            )

        # Check ADD trigger (only if holding and no SELL)
        elif has_position and threshold.add_pb and current_pb <= threshold.add_pb:
            signal_type = SignalType.ADD
            triggered_threshold = threshold.add_pb
            explanation = self._generate_explanation(
                asset, current_pb, threshold.add_pb, "ADD"
            )

        # Check BUY trigger
        elif current_pb <= threshold.buy_pb:
            signal_type = SignalType.BUY
            triggered_threshold = threshold.buy_pb
            explanation = self._generate_explanation(
                asset, current_pb, threshold.buy_pb, "BUY"
            )

        if signal_type:
            # 应用过滤条件
            filter_ok, filter_msg = self.check_filters(asset, signal_type)
            if not filter_ok:
                # 信号被过滤，记录原因但不生成信号
                # 可以考虑记录到日志表，便于分析
                return None

            signal = Signal(
                user_id=self.user_id,
                asset_id=asset.id,
                date=today,
                signal_type=signal_type,
                pb=current_pb,
                triggered_threshold=triggered_threshold,
                explanation=explanation,
                status=SignalStatus.OPEN
            )
            self.session.add(signal)
            self.session.commit()
            return signal

        return None

    def _generate_explanation(
        self,
        asset: Asset,
        current_pb: float,
        threshold_pb: float,
        action: str
    ) -> str:
        """生成可读的信号解释"""
        # Calculate percentile
        percentile = self.valuation_service.calculate_pb_percentile(
            asset.id, current_pb, years=5
        )

        explanation_parts = []

        if action == "BUY":
            explanation_parts.append(
                f"当前 PB={current_pb:.2f} ≤ 请客价 {threshold_pb:.2f}，触发 BUY 信号"
            )
        elif action == "ADD":
            explanation_parts.append(
                f"当前 PB={current_pb:.2f} ≤ 压倒性优势价 {threshold_pb:.2f}，触发 ADD 信号"
            )
        elif action == "SELL":
            explanation_parts.append(
                f"当前 PB={current_pb:.2f} ≥ 退出价 {threshold_pb:.2f}，触发 SELL 信号"
            )

        if percentile is not None:
            explanation_parts.append(f"近5年分位={percentile:.1f}%")
            if percentile <= 15:
                explanation_parts.append("属于历史稀缺低估区间")
            elif percentile <= 30:
                explanation_parts.append("处于相对低估区间")
            elif percentile >= 85:
                explanation_parts.append("处于历史高估区间")

        return "；".join(explanation_parts) + "。"

    def scan_all_stocks(self) -> List[Signal]:
        """扫描所有股票，检测触发信号"""
        assets = self.session.query(Asset).filter(
            Asset.threshold != None,
            Asset.user_id == self.user_id
        ).all()
        signals = []

        for asset in assets:
            signal = self.check_triggers(asset)
            if signal:
                signals.append(signal)

        return signals

    def get_open_signals(self) -> List[Signal]:
        """获取所有未处理的信号"""
        return self.session.query(Signal).filter(
            Signal.user_id == self.user_id,
            Signal.status == SignalStatus.OPEN
        ).order_by(Signal.date.desc()).all()

    def get_today_signals(self) -> List[Signal]:
        """获取今日信号"""
        today = date.today()
        return self.session.query(Signal).filter(
            Signal.user_id == self.user_id,
            Signal.date == today
        ).order_by(Signal.created_at.desc()).all()

    def get_signals_by_status(self, status: SignalStatus) -> List[Signal]:
        """按状态获取信号"""
        return self.session.query(Signal).filter(
            Signal.user_id == self.user_id,
            Signal.status == status
        ).order_by(Signal.date.desc()).all()

    def update_signal_status(self, signal_id: int, status: SignalStatus) -> Optional[Signal]:
        """更新信号状态"""
        signal = self.session.query(Signal).filter(
            Signal.id == signal_id,
            Signal.user_id == self.user_id
        ).first()
        if signal:
            signal.status = status
            self.session.commit()
        return signal

    def get_signal_history(
        self,
        asset_id: Optional[int] = None,
        days: int = 30
    ) -> List[Signal]:
        """获取信号历史"""
        from datetime import timedelta
        start_date = date.today() - timedelta(days=days)

        query = self.session.query(Signal).filter(
            Signal.date >= start_date,
            Signal.user_id == self.user_id
        )

        if asset_id:
            query = query.filter(Signal.asset_id == asset_id)

        return query.order_by(Signal.date.desc()).all()

    def check_roe_quality(self, asset: Asset) -> tuple[bool, Optional[str]]:
        """
        检查ROE质量

        Args:
            asset: 股票资产

        Returns:
            (是否通过, 不通过原因)
        """
        if not self.enable_roe_filter:
            return True, None

        # 这里需要从外部数据源获取ROE数据
        # 目前暂时跳过ROE检查，返回True
        # TODO: 集成 ROE 数据获取
        # 可以从 Tushare/AkShare 获取财务数据
        return True, None

    def check_signal_cooldown(
        self,
        asset_id: int,
        signal_type: SignalType
    ) -> tuple[bool, Optional[str]]:
        """
        检查信号冷却期

        Args:
            asset_id: 股票ID
            signal_type: 信号类型

        Returns:
            (是否可以触发, 冷却原因)
        """
        if not self.enable_cooldown:
            return True, None

        # 检查最近N天是否有相同类型的信号
        cooldown_date = date.today() - timedelta(days=self.signal_cooldown_days)

        recent_signal = self.session.query(Signal).filter(
            Signal.asset_id == asset_id,
            Signal.user_id == self.user_id,
            Signal.signal_type == signal_type,
            Signal.date >= cooldown_date
        ).order_by(Signal.date.desc()).first()

        if recent_signal:
            days_ago = (date.today() - recent_signal.date).days
            return False, f"冷却期内：{days_ago}天前已触发过 {signal_type.value} 信号"

        return True, None

    def check_filters(
        self,
        asset: Asset,
        signal_type: SignalType
    ) -> tuple[bool, Optional[str]]:
        """
        综合检查所有过滤条件

        Args:
            asset: 股票资产
            signal_type: 信号类型

        Returns:
            (是否通过, 不通过原因)
        """
        # 1. ROE质量过滤
        roe_ok, roe_msg = self.check_roe_quality(asset)
        if not roe_ok:
            return False, f"ROE过滤: {roe_msg}"

        # 2. 信号冷却期
        cooldown_ok, cooldown_msg = self.check_signal_cooldown(asset.id, signal_type)
        if not cooldown_ok:
            return False, f"信号冷却: {cooldown_msg}"

        return True, None
