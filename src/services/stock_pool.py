"""Stock pool management service."""
from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from ..database.models import Asset, Threshold, Market


class StockPoolService:
    """管理股票池的增删改查"""

    def __init__(self, session: Session):
        self.session = session

    def add_stock(
        self,
        code: str,
        name: str,
        market: Market,
        industry: Optional[str] = None,
        tags: Optional[str] = None,
        competence_score: int = 3,
        notes: Optional[str] = None,
        buy_pb: Optional[float] = None,
        add_pb: Optional[float] = None,
        sell_pb: Optional[float] = None
    ) -> Asset:
        """添加股票到股票池"""
        # Check if already exists
        existing = self.session.query(Asset).filter(Asset.code == code).first()
        if existing:
            raise ValueError(f"股票 {code} 已存在于股票池中")

        asset = Asset(
            code=code,
            name=name,
            market=market,
            industry=industry,
            tags=tags,
            competence_score=competence_score,
            notes=notes
        )
        self.session.add(asset)
        self.session.flush()  # Get the asset.id

        # Add threshold if buy_pb is provided
        if buy_pb is not None:
            threshold = Threshold(
                asset_id=asset.id,
                buy_pb=buy_pb,
                add_pb=add_pb,
                sell_pb=sell_pb
            )
            self.session.add(threshold)

        self.session.commit()
        return asset

    def remove_stock(self, code: str) -> bool:
        """从股票池删除股票"""
        asset = self.session.query(Asset).filter(Asset.code == code).first()
        if asset:
            self.session.delete(asset)
            self.session.commit()
            return True
        return False

    def get_stock(self, code: str) -> Optional[Asset]:
        """获取单只股票信息"""
        return self.session.query(Asset).filter(Asset.code == code).first()

    def get_all_stocks(self) -> List[Asset]:
        """获取所有股票"""
        return self.session.query(Asset).order_by(Asset.created_at.desc()).all()

    def update_stock(
        self,
        code: str,
        name: Optional[str] = None,
        industry: Optional[str] = None,
        tags: Optional[str] = None,
        competence_score: Optional[int] = None,
        ai_score: Optional[int] = None,
        ai_suggestion: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Optional[Asset]:
        """更新股票信息"""
        asset = self.get_stock(code)
        if not asset:
            return None

        if name is not None:
            asset.name = name
        if industry is not None:
            asset.industry = industry
        if tags is not None:
            asset.tags = tags
        if competence_score is not None:
            asset.competence_score = competence_score
        if ai_score is not None:
            asset.ai_score = ai_score
        if ai_suggestion is not None:
            asset.ai_suggestion = ai_suggestion
        if notes is not None:
            asset.notes = notes

        asset.updated_at = datetime.now()
        self.session.commit()
        return asset

    def update_threshold(
        self,
        code: str,
        buy_pb: float,
        add_pb: Optional[float] = None,
        sell_pb: Optional[float] = None
    ) -> Optional[Threshold]:
        """更新股票的PB阈值"""
        asset = self.get_stock(code)
        if not asset:
            return None

        if asset.threshold:
            asset.threshold.buy_pb = buy_pb
            asset.threshold.add_pb = add_pb
            asset.threshold.sell_pb = sell_pb
            asset.threshold.updated_at = datetime.now()
        else:
            threshold = Threshold(
                asset_id=asset.id,
                buy_pb=buy_pb,
                add_pb=add_pb,
                sell_pb=sell_pb
            )
            self.session.add(threshold)

        self.session.commit()
        return asset.threshold

    def get_stocks_by_market(self, market: Market) -> List[Asset]:
        """按市场筛选股票"""
        return self.session.query(Asset).filter(Asset.market == market).all()

    def get_stocks_by_competence(self, min_score: int = 4) -> List[Asset]:
        """获取高关注指数的股票"""
        return self.session.query(Asset).filter(Asset.competence_score >= min_score).all()

    def search_stocks(self, keyword: str) -> List[Asset]:
        """搜索股票（按代码或名称）"""
        pattern = f"%{keyword}%"
        return self.session.query(Asset).filter(
            (Asset.code.like(pattern)) | (Asset.name.like(pattern))
        ).all()
