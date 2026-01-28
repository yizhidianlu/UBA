"""Real-time data fetching service using Tushare."""
from typing import Optional, Dict, List
from datetime import datetime, date, timedelta
from dataclasses import dataclass

try:
    import tushare as ts
    TUSHARE_AVAILABLE = True
except ImportError:
    TUSHARE_AVAILABLE = False


@dataclass
class RealtimeQuote:
    """实时行情数据（使用Tushare日频数据）"""
    code: str
    name: str
    price: float
    change: float
    change_pct: float
    pb: Optional[float]
    pe: Optional[float]
    volume: int
    amount: float
    high: float
    low: float
    open: float
    prev_close: float
    update_time: datetime


class RealtimeService:
    """实时数据服务 - 基于 Tushare"""

    def __init__(self):
        self._cache: Dict[str, RealtimeQuote] = {}
        self._cache_time: Optional[datetime] = None
        self._pro = None
        self._init_tushare()

    def _init_tushare(self):
        """初始化 Tushare"""
        if not TUSHARE_AVAILABLE:
            print("Tushare 未安装")
            return

        try:
            from src.services.stock_analyzer import get_tushare_token
            token = get_tushare_token()
            if token:
                ts.set_token(token)
                self._pro = ts.pro_api()
        except Exception as e:
            print(f"Tushare 初始化失败: {e}")

    def _normalize_code(self, code: str) -> str:
        """规范化股票代码为Tushare格式"""
        code = code.upper().strip()
        if '.SH' in code or '.SZ' in code or '.HK' in code:
            return code

        # 根据代码开头判断市场
        if code.startswith('6'):
            return f"{code}.SH"
        elif code.startswith(('0', '3')):
            return f"{code}.SZ"
        else:
            return f"{code}.SH"

    def get_realtime_quote(self, code: str) -> Optional[RealtimeQuote]:
        """获取股票行情（使用Tushare最新日频数据）"""
        if not self._pro:
            print("Tushare API 未初始化")
            return None

        ts_code = self._normalize_code(code)

        try:
            # 获取最近几天的日频数据
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=10)).strftime('%Y%m%d')

            # 获取日K线数据
            df_daily = self._pro.daily(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date
            )

            if df_daily is None or df_daily.empty:
                print(f"未找到K线数据: {ts_code}")
                return None

            # 获取最新交易日数据
            latest = df_daily.iloc[0]

            # 获取前一交易日收盘价
            prev_close = df_daily.iloc[1]['close'] if len(df_daily) > 1 else latest['close']

            # 获取基本面数据（PB、PE）
            df_basic = self._pro.daily_basic(
                ts_code=ts_code,
                start_date=latest['trade_date'],
                end_date=latest['trade_date'],
                fields='ts_code,trade_date,pb,pe'
            )

            pb = None
            pe = None
            if df_basic is not None and not df_basic.empty:
                pb = df_basic.iloc[0]['pb'] if 'pb' in df_basic.columns else None
                pe = df_basic.iloc[0]['pe'] if 'pe' in df_basic.columns else None

            # 获取股票名称
            df_info = self._pro.stock_basic(ts_code=ts_code, fields='ts_code,name')
            name = df_info.iloc[0]['name'] if df_info is not None and not df_info.empty else ts_code

            # 计算涨跌幅
            price = latest['close']
            change = price - prev_close
            change_pct = (change / prev_close * 100) if prev_close > 0 else 0

            return RealtimeQuote(
                code=ts_code,
                name=name,
                price=price,
                change=change,
                change_pct=change_pct,
                pb=pb,
                pe=pe,
                volume=int(latest['vol']) if 'vol' in latest else 0,
                amount=latest['amount'] if 'amount' in latest else 0,
                high=latest['high'] if 'high' in latest else price,
                low=latest['low'] if 'low' in latest else price,
                open=latest['open'] if 'open' in latest else price,
                prev_close=prev_close,
                update_time=datetime.now()
            )

        except Exception as e:
            print(f"获取行情失败 {ts_code}: {e}")
            import traceback
            traceback.print_exc()

        return None

    def get_batch_quotes(self, codes: List[str]) -> Dict[str, RealtimeQuote]:
        """批量获取实时行情 - 使用 Tushare"""
        results = {}

        if not self._pro:
            print("Tushare API 未初始化，无法批量获取行情")
            return results

        # 逐个获取（Tushare 不支持真正的批量实时行情）
        for code in codes:
            try:
                quote = self.get_realtime_quote(code)
                if quote:
                    results[quote.code] = quote
            except Exception as e:
                print(f"获取 {code} 行情失败: {e}")
                continue

        self._cache = results
        self._cache_time = datetime.now()

        return results

    def get_cached_quotes(self) -> Dict[str, RealtimeQuote]:
        """获取缓存的行情数据"""
        return self._cache

    def get_cache_time(self) -> Optional[datetime]:
        """获取缓存更新时间"""
        return self._cache_time
