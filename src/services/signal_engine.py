"""Signal engine for PB trigger detection."""
from typing import List, Optional
from datetime import date, datetime
from sqlalchemy.orm import Session

from ..database.models import Asset, Signal, SignalType, SignalStatus, Valuation
from .valuation import ValuationService


class SignalEngine:
    """信号引擎：检测PB触发并生成信号"""

    def __init__(self, session: Session):
        self.session = session
        self.valuation_service = ValuationService(session)

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
            signal = Signal(
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
        assets = self.session.query(Asset).filter(Asset.threshold != None).all()
        signals = []

        for asset in assets:
            signal = self.check_triggers(asset)
            if signal:
                signals.append(signal)

        return signals

    def get_open_signals(self) -> List[Signal]:
        """获取所有未处理的信号"""
        return self.session.query(Signal).filter(
            Signal.status == SignalStatus.OPEN
        ).order_by(Signal.date.desc()).all()

    def get_today_signals(self) -> List[Signal]:
        """获取今日信号"""
        today = date.today()
        return self.session.query(Signal).filter(
            Signal.date == today
        ).order_by(Signal.created_at.desc()).all()

    def get_signals_by_status(self, status: SignalStatus) -> List[Signal]:
        """按状态获取信号"""
        return self.session.query(Signal).filter(
            Signal.status == status
        ).order_by(Signal.date.desc()).all()

    def update_signal_status(self, signal_id: int, status: SignalStatus) -> Optional[Signal]:
        """更新信号状态"""
        signal = self.session.query(Signal).filter(Signal.id == signal_id).first()
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

        query = self.session.query(Signal).filter(Signal.date >= start_date)

        if asset_id:
            query = query.filter(Signal.asset_id == asset_id)

        return query.order_by(Signal.date.desc()).all()
