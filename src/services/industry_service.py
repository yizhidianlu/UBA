"""
行业配置服务
提供行业默认阈值、风险参数等配置
"""
from typing import Optional, List, Dict
from sqlalchemy.orm import Session

from ..database.models import IndustryConfig


class IndustryService:
    """行业配置服务"""

    def __init__(self, session: Session):
        self.session = session

    def get_industry_config(self, industry_name: str) -> Optional[IndustryConfig]:
        """获取行业配置"""
        return self.session.query(IndustryConfig).filter(
            IndustryConfig.industry_name == industry_name
        ).first()

    def get_all_industries(self) -> List[IndustryConfig]:
        """获取所有行业配置"""
        return self.session.query(IndustryConfig).order_by(
            IndustryConfig.industry_name
        ).all()

    def get_industry_thresholds(
        self,
        industry_name: str
    ) -> Optional[Dict[str, float]]:
        """
        获取行业默认阈值

        Returns:
            包含 buy_pb, add_pb, sell_pb 的字典，如果行业不存在则返回None
        """
        config = self.get_industry_config(industry_name)
        if not config:
            return None

        return {
            'buy_pb': config.default_buy_pb,
            'add_pb': config.default_add_pb,
            'sell_pb': config.default_sell_pb,
            'typical_pb_min': config.typical_pb_range_min,
            'typical_pb_max': config.typical_pb_range_max,
            'typical_roe': config.typical_roe,
            'recommended_max_position': config.recommended_max_position,
            'risk_level': config.risk_level,
            'cyclical': config.cyclical
        }

    def create_or_update_industry(
        self,
        industry_name: str,
        display_name: str = None,
        description: str = None,
        default_buy_pb: float = None,
        default_add_pb: float = None,
        default_sell_pb: float = None,
        typical_pb_range_min: float = None,
        typical_pb_range_max: float = None,
        typical_roe: float = None,
        cyclical: bool = False,
        recommended_max_position: float = None,
        risk_level: str = "medium"
    ) -> IndustryConfig:
        """创建或更新行业配置"""
        config = self.get_industry_config(industry_name)

        if config:
            # 更新现有配置
            if display_name is not None:
                config.display_name = display_name
            if description is not None:
                config.description = description
            if default_buy_pb is not None:
                config.default_buy_pb = default_buy_pb
            if default_add_pb is not None:
                config.default_add_pb = default_add_pb
            if default_sell_pb is not None:
                config.default_sell_pb = default_sell_pb
            if typical_pb_range_min is not None:
                config.typical_pb_range_min = typical_pb_range_min
            if typical_pb_range_max is not None:
                config.typical_pb_range_max = typical_pb_range_max
            if typical_roe is not None:
                config.typical_roe = typical_roe
            if cyclical is not None:
                config.cyclical = cyclical
            if recommended_max_position is not None:
                config.recommended_max_position = recommended_max_position
            if risk_level is not None:
                config.risk_level = risk_level
        else:
            # 创建新配置
            config = IndustryConfig(
                industry_name=industry_name,
                display_name=display_name or industry_name,
                description=description,
                default_buy_pb=default_buy_pb,
                default_add_pb=default_add_pb,
                default_sell_pb=default_sell_pb,
                typical_pb_range_min=typical_pb_range_min,
                typical_pb_range_max=typical_pb_range_max,
                typical_roe=typical_roe,
                cyclical=cyclical,
                recommended_max_position=recommended_max_position,
                risk_level=risk_level
            )
            self.session.add(config)

        self.session.commit()
        return config

    def get_risk_adjusted_thresholds(
        self,
        industry_name: str,
        risk_preference: str = "moderate"
    ) -> Optional[Dict[str, float]]:
        """
        根据风险偏好调整阈值

        Args:
            industry_name: 行业名称
            risk_preference: 风险偏好 (conservative/moderate/aggressive)

        Returns:
            调整后的阈值字典
        """
        thresholds = self.get_industry_thresholds(industry_name)
        if not thresholds:
            return None

        # 根据风险偏好调整
        if risk_preference == "conservative":
            # 保守型：更严格的买入条件，更早的卖出
            thresholds['buy_pb'] = thresholds['buy_pb'] * 0.9
            thresholds['add_pb'] = thresholds['add_pb'] * 0.85
            thresholds['sell_pb'] = thresholds['sell_pb'] * 0.95
        elif risk_preference == "aggressive":
            # 激进型：更宽松的买入条件，更晚的卖出
            thresholds['buy_pb'] = thresholds['buy_pb'] * 1.1
            thresholds['add_pb'] = thresholds['add_pb'] * 1.15
            thresholds['sell_pb'] = thresholds['sell_pb'] * 1.05

        return thresholds
