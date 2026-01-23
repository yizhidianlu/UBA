"""Valuation data fetching and management service."""
from typing import List, Optional, Tuple
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
import pandas as pd
import threading

from ..database.models import Asset, Valuation


class ValuationService:
    """PB数据获取与管理"""

    def __init__(self, session: Session):
        self.session = session

    _pb_fetch_lock = threading.Lock()

    def fetch_pb_data(
        self,
        code: str,
        start_date: Optional[date] = None,
        allow_wait: bool = True
    ) -> Optional[List[dict]]:
        """
        从数据源获取PB数据
        使用akshare获取A股/港股数据
        """
        if allow_wait:
            acquired = self._pb_fetch_lock.acquire()
        else:
            acquired = self._pb_fetch_lock.acquire(blocking=False)
        if not acquired:
            print("PB数据获取正在进行，已跳过重复请求")
            return None

        try:
            try:
                import akshare as ak
            except ImportError:
                raise ImportError("请安装akshare: pip install akshare")

            if start_date is None:
                start_date = date.today() - timedelta(days=365 * 5)  # 默认5年

            data_list = []

            # Parse code to determine market
            if code.endswith('.SH') or code.endswith('.SZ'):
                # A股
                symbol = code.split('.')[0]
                try:
                    # 尝试获取个股指标数据
                    df = ak.stock_a_lg_indicator(symbol=symbol)
                    if df is not None and not df.empty:
                        df = df[df['trade_date'] >= start_date.strftime('%Y-%m-%d')]
                        for _, row in df.iterrows():
                            data_list.append({
                                'date': pd.to_datetime(row['trade_date']).date(),
                                'pb': float(row['pb']) if pd.notna(row.get('pb')) else None,
                                'price': float(row['total_mv']) / 10000 if pd.notna(row.get('total_mv')) else None,
                            })
                except Exception as e:
                    print(f"获取A股数据失败 {code}: {e}")
                    # 尝试备用方法
                    try:
                        df = ak.stock_zh_a_hist(symbol=symbol, period="daily",
                                               start_date=start_date.strftime('%Y%m%d'),
                                               adjust="qfq")
                        if df is not None and not df.empty:
                            for _, row in df.iterrows():
                                data_list.append({
                                    'date': pd.to_datetime(row['日期']).date(),
                                    'pb': None,  # 此接口无PB数据
                                    'price': float(row['收盘']),
                                })
                    except Exception as e2:
                        print(f"备用方法也失败 {code}: {e2}")

            elif code.endswith('.HK'):
                # 港股
                symbol = code.replace('.HK', '')
                try:
                    df = ak.stock_hk_hist(symbol=symbol, period="daily",
                                         start_date=start_date.strftime('%Y%m%d'),
                                         adjust="qfq")
                    if df is not None and not df.empty:
                        for _, row in df.iterrows():
                            data_list.append({
                                'date': pd.to_datetime(row['日期']).date(),
                                'pb': None,  # 港股历史PB需要其他数据源
                                'price': float(row['收盘']),
                            })
                except Exception as e:
                    print(f"获取港股数据失败 {code}: {e}")

            return data_list
        finally:
            self._pb_fetch_lock.release()

    def save_valuation(
        self,
        asset_id: int,
        val_date: date,
        pb: float,
        price: Optional[float] = None,
        book_value_per_share: Optional[float] = None,
        data_source: str = "akshare"
    ) -> Valuation:
        """保存单条估值数据"""
        # Check if exists
        existing = self.session.query(Valuation).filter(
            Valuation.asset_id == asset_id,
            Valuation.date == val_date
        ).first()

        if existing:
            existing.pb = pb
            existing.price = price
            existing.book_value_per_share = book_value_per_share
            existing.data_source = data_source
            existing.fetched_at = datetime.now()
            self.session.commit()
            return existing

        valuation = Valuation(
            asset_id=asset_id,
            date=val_date,
            pb=pb,
            price=price,
            book_value_per_share=book_value_per_share,
            data_source=data_source
        )
        self.session.add(valuation)
        self.session.commit()
        return valuation

    def batch_save_valuations(self, asset_id: int, data_list: List[dict]) -> int:
        """批量保存估值数据"""
        count = 0
        for data in data_list:
            if data.get('pb') is not None:
                self.save_valuation(
                    asset_id=asset_id,
                    val_date=data['date'],
                    pb=data['pb'],
                    price=data.get('price'),
                    book_value_per_share=data.get('book_value_per_share')
                )
                count += 1
        return count

    def update_all_stocks(self) -> dict:
        """更新所有股票的PB数据"""
        assets = self.session.query(Asset).all()
        results = {'success': [], 'failed': []}

        for asset in assets:
            try:
                data_list = self.fetch_pb_data(asset.code)
                if data_list is None:
                    results['failed'].append({'code': asset.code, 'error': 'PB数据获取正在进行'})
                else:
                    count = self.batch_save_valuations(asset.id, data_list)
                    results['success'].append({'code': asset.code, 'count': count})
            except Exception as e:
                results['failed'].append({'code': asset.code, 'error': str(e)})

        return results

    def get_latest_pb(self, asset_id: int) -> Optional[Valuation]:
        """获取最新PB"""
        return self.session.query(Valuation).filter(
            Valuation.asset_id == asset_id
        ).order_by(Valuation.date.desc()).first()

    def get_pb_history(
        self,
        asset_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[Valuation]:
        """获取PB历史数据"""
        query = self.session.query(Valuation).filter(Valuation.asset_id == asset_id)

        if start_date:
            query = query.filter(Valuation.date >= start_date)
        if end_date:
            query = query.filter(Valuation.date <= end_date)

        return query.order_by(Valuation.date).all()

    def calculate_pb_percentile(
        self,
        asset_id: int,
        current_pb: float,
        years: int = 5
    ) -> Optional[float]:
        """计算当前PB在历史N年中的分位数"""
        start_date = date.today() - timedelta(days=365 * years)

        # Get all historical PB values
        valuations = self.session.query(Valuation.pb).filter(
            Valuation.asset_id == asset_id,
            Valuation.date >= start_date,
            Valuation.pb.isnot(None)
        ).all()

        if not valuations:
            return None

        pb_values = sorted([v.pb for v in valuations])
        count_below = sum(1 for pb in pb_values if pb <= current_pb)

        return (count_below / len(pb_values)) * 100

    def get_pb_stats(self, asset_id: int, years: int = 5) -> Optional[dict]:
        """获取PB统计信息"""
        start_date = date.today() - timedelta(days=365 * years)

        result = self.session.query(
            func.min(Valuation.pb).label('min_pb'),
            func.max(Valuation.pb).label('max_pb'),
            func.avg(Valuation.pb).label('avg_pb'),
            func.count(Valuation.pb).label('count')
        ).filter(
            Valuation.asset_id == asset_id,
            Valuation.date >= start_date,
            Valuation.pb.isnot(None)
        ).first()

        if not result or result.count == 0:
            return None

        return {
            'min_pb': result.min_pb,
            'max_pb': result.max_pb,
            'avg_pb': result.avg_pb,
            'count': result.count,
            'years': years
        }
