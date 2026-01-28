"""Stock analysis service using Tushare for all data."""
from typing import Optional, Tuple, List, Dict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import os
import time
import json
import threading

# Try to import tushare
try:
    import tushare as ts
    TUSHARE_AVAILABLE = True
except ImportError:
    TUSHARE_AVAILABLE = False

# 缓存目录
CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data')
STOCK_BASIC_CACHE = os.path.join(CACHE_DIR, 'stock_basic_cache.json')

# 全局股票列表缓存
_stock_basic_cache: Dict[str, dict] = {}
_stock_basic_cache_time: Optional[datetime] = None
_cache_lock = threading.Lock()


def get_tushare_token() -> Optional[str]:
    """
    从环境变量或Streamlit secrets获取Tushare token
    优先级: Streamlit secrets > 环境变量
    """
    # 1. 尝试从 Streamlit secrets 获取
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and "TUSHARE_TOKEN" in st.secrets:
            return st.secrets["TUSHARE_TOKEN"]
    except Exception:
        pass

    # 2. 从环境变量获取
    token = os.getenv("TUSHARE_TOKEN")
    if token:
        return token

    # 3. 无token时返回None，调用方需处理降级
    return None


@dataclass
class StockInfo:
    """股票基本信息"""
    code: str
    name: str
    industry: str
    market: str


@dataclass
class PBAnalysis:
    """PB分析结果"""
    current_pb: Optional[float]
    min_pb: float
    max_pb: float
    avg_pb: float
    median_pb: float
    percentile_15: float
    percentile_10: float
    data_count: int
    data_years: float
    recommended_buy_pb: float
    recommended_add_pb: float
    recommended_sell_pb: float
    pb_history: list


def _load_stock_basic_cache() -> Dict[str, dict]:
    """从文件加载股票基本信息缓存"""
    global _stock_basic_cache, _stock_basic_cache_time

    with _cache_lock:
        if _stock_basic_cache and _stock_basic_cache_time:
            # 缓存有效期24小时
            if (datetime.now() - _stock_basic_cache_time).total_seconds() < 86400:
                return _stock_basic_cache

        try:
            if os.path.exists(STOCK_BASIC_CACHE):
                with open(STOCK_BASIC_CACHE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    cache_time = datetime.fromisoformat(data.get('timestamp', '2000-01-01'))
                    # 缓存有效期24小时
                    if (datetime.now() - cache_time).total_seconds() < 86400:
                        _stock_basic_cache = {s['ts_code']: s for s in data.get('stocks', [])}
                        _stock_basic_cache_time = cache_time
                        return _stock_basic_cache
        except Exception as e:
            print(f"加载股票缓存失败: {e}")

        return {}


def _save_stock_basic_cache(stocks: List[dict]):
    """保存股票基本信息到缓存文件"""
    global _stock_basic_cache, _stock_basic_cache_time

    with _cache_lock:
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(STOCK_BASIC_CACHE, 'w', encoding='utf-8') as f:
                json.dump({
                    'timestamp': datetime.now().isoformat(),
                    'stocks': stocks
                }, f, ensure_ascii=False)
            _stock_basic_cache = {s['ts_code']: s for s in stocks}
            _stock_basic_cache_time = datetime.now()
        except Exception as e:
            print(f"保存股票缓存失败: {e}")


class StockAnalyzer:
    """股票分析器：使用 Tushare 获取所有数据"""

    # API调用间隔（秒）- 避免触发速率限制
    API_CALL_INTERVAL = 0.5
    _last_api_call: Optional[datetime] = None
    _api_lock = threading.Lock()

    def __init__(self, token: Optional[str] = None):

        # Tushare API
        self.pro = None
        if TUSHARE_AVAILABLE:
            try:
                # 优先使用传入的token，否则从环境变量/secrets获取
                if token is None:
                    token = get_tushare_token()

                if token:
                    ts.set_token(token)
                    self.pro = ts.pro_api()
                else:
                    print("未配置 Tushare Token，无法获取数据")
            except Exception as e:
                print(f"Tushare初始化失败: {e}")

    def _rate_limit(self):
        """API调用速率限制"""
        with self._api_lock:
            if self._last_api_call:
                elapsed = (datetime.now() - self._last_api_call).total_seconds()
                if elapsed < self.API_CALL_INTERVAL:
                    time.sleep(self.API_CALL_INTERVAL - elapsed)
            StockAnalyzer._last_api_call = datetime.now()

    def _ensure_stock_cache(self) -> Dict[str, dict]:
        """确保股票基本信息缓存可用"""
        cache = _load_stock_basic_cache()
        if cache:
            return cache

        # 缓存为空，需要重新获取
        if not self.pro:
            return {}

        try:
            self._rate_limit()
            df = self.pro.stock_basic(
                exchange='',
                list_status='L',
                fields='ts_code,symbol,name,industry,market'
            )

            if df is not None and not df.empty:
                stocks = df.to_dict('records')
                _save_stock_basic_cache(stocks)
                return {s['ts_code']: s for s in stocks}
        except Exception as e:
            print(f"获取股票列表失败: {e}")

        return {}

    def parse_code(self, code: str) -> Tuple[str, str, str]:
        """
        解析股票代码
        返回: (tushare格式, 市场, 东财secid)
        """
        code = code.strip().upper()

        # 处理各种格式
        if '.SH' in code:
            pure_code = code.replace('.SH', '')
            ts_code = code
            secid = f"1.{pure_code}"
            return ts_code, "A股", secid

        if '.SZ' in code:
            pure_code = code.replace('.SZ', '')
            ts_code = code
            secid = f"0.{pure_code}"
            return ts_code, "A股", secid

        if '.HK' in code:
            pure_code = code.replace('.HK', '')
            ts_code = code
            secid = f"116.{pure_code.zfill(5)}"
            return ts_code, "港股", secid

        if code.startswith('SH'):
            pure_code = code[2:]
            ts_code = pure_code + ".SH"
            secid = f"1.{pure_code}"
            return ts_code, "A股", secid

        if code.startswith('SZ'):
            pure_code = code[2:]
            ts_code = pure_code + ".SZ"
            secid = f"0.{pure_code}"
            return ts_code, "A股", secid

        # 纯数字
        pure_code = code
        if pure_code.startswith('6'):
            ts_code = pure_code + ".SH"
            secid = f"1.{pure_code}"
        elif pure_code.startswith(('0', '3')):
            ts_code = pure_code + ".SZ"
            secid = f"0.{pure_code}"
        else:
            ts_code = pure_code + ".SH"
            secid = f"1.{pure_code}"

        return ts_code, "A股", secid

    def get_stock_info(self, code: str) -> Optional[StockInfo]:
        """使用 Tushare 获取股票基本信息（优先使用缓存）"""
        ts_code, market, secid = self.parse_code(code)

        # 1. 先从缓存获取
        cache = self._ensure_stock_cache()
        if ts_code in cache:
            stock = cache[ts_code]
            return StockInfo(
                code=ts_code,
                name=stock['name'],
                industry=stock.get('industry', '') or '',
                market=market
            )

        # 2. 缓存中没有，尝试API查询
        if not self.pro:
            print("Tushare API 未初始化，无法获取股票信息")
            return None

        try:
            self._rate_limit()
            df = self.pro.stock_basic(ts_code=ts_code, fields='ts_code,name,industry,market')

            if df is not None and not df.empty:
                row = df.iloc[0]
                return StockInfo(
                    code=ts_code,
                    name=row['name'],
                    industry=row['industry'] if 'industry' in row and row['industry'] else "",
                    market=market
                )
            else:
                print(f"Tushare 未找到股票信息: {ts_code}")
        except Exception as e:
            print(f"获取股票信息失败: {e}")

        return None

    def fetch_pb_history(self, code: str, years: int = 5) -> List[dict]:
        """获取历史PB数据 - 使用 Tushare"""
        ts_code, market, secid = self.parse_code(code)
        pb_data = []

        # 只使用 Tushare
        if self.pro and market == "A股":
            pb_data = self._fetch_pb_tushare(ts_code, years)
            if not pb_data:
                print(f"Tushare 未找到 {ts_code} 的PB数据")
        else:
            print(f"Tushare API 未初始化或股票市场不支持: {market}")

        return pb_data

    def _fetch_pb_tushare(self, ts_code: str, years: int) -> List[dict]:
        """使用Tushare获取PB数据

        注意：此接口需要 Tushare 120+ 积分权限
        详情请参考：https://tushare.pro/document/1?doc_id=108
        """
        pb_data = []

        try:
            self._rate_limit()
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=365 * years)).strftime('%Y%m%d')

            df = self.pro.daily_basic(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                fields='trade_date,close,pb'
            )

            if df is not None and not df.empty:
                df = df.sort_values('trade_date', ascending=False)

                for _, row in df.iterrows():
                    try:
                        pb_val = row.get('pb')
                        if pb_val is not None and float(pb_val) > 0:
                            trade_date = datetime.strptime(str(int(row['trade_date'])), '%Y%m%d').date()
                            pb_data.append({
                                'date': trade_date,
                                'pb': round(float(pb_val), 2),
                                'price': float(row['close']) if row.get('close') else None,
                                'data_source': 'tushare',
                                'pb_method': 'direct'
                            })
                    except Exception:
                        continue

        except Exception as e:
            error_msg = str(e)
            if '权限' in error_msg or 'permission' in error_msg.lower():
                print(f"Tushare获取PB失败: 需要120+积分权限访问daily_basic接口")
                print("请前往 https://tushare.pro/document/1?doc_id=108 查看权限说明")
            else:
                print(f"Tushare获取PB失败: {e}")

        return pb_data


    def analyze_pb(self, pb_data: List[dict]) -> Optional[PBAnalysis]:
        """分析PB并给出推荐价格"""
        if not pb_data:
            return None

        pb_values = [d['pb'] for d in pb_data if d.get('pb') and d['pb'] > 0]

        if len(pb_values) < 10:
            return None

        sorted_pbs = sorted(pb_values)
        n = len(sorted_pbs)

        min_pb = sorted_pbs[0]
        max_pb = sorted_pbs[-1]
        avg_pb = sum(sorted_pbs) / n
        median_pb = sorted_pbs[n // 2]

        percentile_10 = sorted_pbs[int(n * 0.10)]
        percentile_15 = sorted_pbs[int(n * 0.15)]
        percentile_75 = sorted_pbs[int(n * 0.75)]

        recommended_buy_pb = round(percentile_15, 2)  # 请客价: 15%分位 (更严格)
        recommended_add_pb = round(percentile_10, 2)  # 加仓价: 10%分位
        recommended_sell_pb = round(percentile_75, 2) # 退出价: 75%分位

        current_pb = pb_data[0]['pb'] if pb_data and pb_data[0].get('pb') else None

        if len(pb_data) >= 2:
            valid_dates = [d['date'] for d in pb_data if d.get('date')]
            if len(valid_dates) >= 2:
                date_range = (valid_dates[0] - valid_dates[-1]).days
                data_years = round(abs(date_range) / 365, 1)
            else:
                data_years = 0
        else:
            data_years = 0

        pb_history = [(d['date'], d['pb']) for d in pb_data if d.get('pb') and d['pb'] > 0]

        return PBAnalysis(
            current_pb=current_pb,
            min_pb=round(min_pb, 2),
            max_pb=round(max_pb, 2),
            avg_pb=round(avg_pb, 2),
            median_pb=round(median_pb, 2),
            percentile_15=round(percentile_15, 2),
            percentile_10=round(percentile_10, 2),
            data_count=len(pb_values),
            data_years=data_years,
            recommended_buy_pb=recommended_buy_pb,
            recommended_add_pb=recommended_add_pb,
            recommended_sell_pb=recommended_sell_pb,
            pb_history=pb_history
        )

    def full_analysis(self, code: str) -> dict:
        """完整分析"""
        result = {
            'success': False,
            'code': code,
            'stock_info': None,
            'pb_analysis': None,
            'error': None
        }

        stock_info = self.get_stock_info(code)
        if not stock_info:
            result['error'] = f"无法获取股票信息，请检查代码是否正确: {code}"
            return result

        result['stock_info'] = stock_info

        pb_data = self.fetch_pb_history(stock_info.code, years=5)

        if pb_data:
            pb_analysis = self.analyze_pb(pb_data)
            if pb_analysis:
                result['pb_analysis'] = pb_analysis
            else:
                result['error'] = "PB数据不足，无法进行分析"
        else:
            result['error'] = "无法获取PB历史数据"

        result['success'] = True
        return result

    def search_stock_by_name(self, keyword: str, limit: int = 10) -> List[StockInfo]:
        """
        根据股票名称或代码关键词搜索股票 - 使用缓存

        Args:
            keyword: 搜索关键词（股票名称或代码）
            limit: 返回结果数量限制

        Returns:
            匹配的股票列表
        """
        results = []

        # 从缓存搜索
        cache = self._ensure_stock_cache()
        if not cache:
            print("股票缓存为空，无法搜索")
            return results

        try:
            keyword_lower = keyword.lower()
            keyword_upper = keyword.upper()

            for ts_code, stock in cache.items():
                name = stock.get('name', '')
                # 名称或代码包含关键词
                if keyword_lower in name.lower() or keyword_upper in ts_code:
                    results.append(StockInfo(
                        code=ts_code,
                        name=name,
                        industry=stock.get('industry', '') or '',
                        market="A股"
                    ))
                    if len(results) >= limit:
                        break

        except Exception as e:
            print(f"搜索股票失败: {e}")

        return results[:limit]


