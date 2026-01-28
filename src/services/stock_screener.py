"""Stock screening service to find undervalued stocks based on PB - Tushare version."""
from typing import Optional, List, Dict
from dataclasses import dataclass
from datetime import datetime, timedelta
import time

try:
    import tushare as ts
    TUSHARE_AVAILABLE = True
except ImportError:
    ts = None
    TUSHARE_AVAILABLE = False


@dataclass
class StockRecommendation:
    """股票推荐结果"""
    code: str
    name: str
    industry: str
    current_price: float
    current_pb: float
    recommended_buy_pb: float
    pb_distance_pct: float  # 距离请客价的百分比
    min_pb: float
    max_pb: float
    avg_pb: float
    market_cap: float  # 市值(亿)
    pe_ttm: Optional[float]
    roe: Optional[float]


class StockScreener:
    """股票筛选器：寻找PB接近请客价的股票 - 使用 Tushare"""

    # 热门行业股票池 - 各行业代表性股票
    STOCK_UNIVERSE = [
        # 白酒
        "600519", "000858", "000568", "002304", "603369", "000799", "600779", "000596",
        # 银行
        "601398", "601939", "601288", "600036", "000001", "601166", "600000", "601818",
        # 保险
        "601318", "601628", "601336", "601601",
        # 家电
        "000651", "000333", "002050", "000100", "002032",
        # 医药
        "600276", "000538", "600196", "002007", "300760", "603259", "000963",
        # 食品饮料
        "603288", "002714", "600887", "000895", "600809",
        # 地产
        "000002", "001979", "600048", "000069", "600383",
        # 建材
        "600585", "000401", "002271",
        # 消费
        "600690", "002024", "603868", "002557",
        # 科技
        "000725", "002415", "300750", "002230", "603501",
        # 新能源
        "300014", "002594", "600438", "601012",
        # 汽车
        "600104", "000625", "601238", "002594",
        # 券商
        "600030", "601688", "000776", "601211",
        # 电力
        "600900", "601985", "600886",
    ]

    def __init__(self):
        self._pro = None
        self._init_tushare()

    def _init_tushare(self):
        """初始化 Tushare API"""
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

    def _get_ts_code(self, code: str) -> str:
        """转换股票代码为 Tushare 格式"""
        code = code.upper().replace('.SH', '').replace('.SZ', '')
        if code.startswith('6'):
            return f"{code}.SH"
        else:
            return f"{code}.SZ"

    def _fetch_stock_data(self, code: str) -> Optional[Dict]:
        """获取单只股票的详细数据 - 使用 Tushare"""
        if not self._pro:
            return None

        ts_code = self._get_ts_code(code)

        try:
            # 从缓存获取股票基本信息
            from src.services.stock_analyzer import _load_stock_basic_cache
            cache = _load_stock_basic_cache()

            name = ''
            industry = ''
            if ts_code in cache:
                name = cache[ts_code].get('name', '')
                industry = cache[ts_code].get('industry', '') or ''

            # 获取最新日行情
            time.sleep(0.5)
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=10)).strftime('%Y%m%d')

            df_daily = self._pro.daily(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date
            )

            if df_daily is None or df_daily.empty:
                return None

            price = df_daily.iloc[0]['close']

            # 获取 PB、PE、市值
            time.sleep(0.5)
            df_basic = self._pro.daily_basic(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                fields='ts_code,trade_date,pb,pe_ttm,total_mv'
            )

            if df_basic is None or df_basic.empty:
                return None

            latest = df_basic.iloc[0]
            current_pb = latest['pb'] if 'pb' in latest and latest['pb'] else None
            pe_ttm = latest['pe_ttm'] if 'pe_ttm' in latest else None
            market_cap = latest['total_mv'] / 10000 if 'total_mv' in latest and latest['total_mv'] else None

            if not current_pb or current_pb <= 0:
                return None

            return {
                'code': ts_code,
                'name': name,
                'industry': industry,
                'price': price,
                'current_pb': round(current_pb, 2),
                'market_cap': market_cap,
                'pe_ttm': pe_ttm,
            }

        except Exception as e:
            error_msg = str(e)
            if '权限' in error_msg:
                print(f"获取股票数据需要更高的 Tushare 权限: {ts_code}")
            else:
                print(f"获取股票数据失败 {code}: {e}")
            return None

    def _fetch_pb_history(self, ts_code: str, years: int = 3) -> List[float]:
        """获取历史PB数据 - 使用 Tushare"""
        pb_values = []

        if not self._pro:
            return pb_values

        try:
            time.sleep(0.5)
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=365 * years)).strftime('%Y%m%d')

            df = self._pro.daily_basic(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                fields='trade_date,pb'
            )

            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    pb = row.get('pb')
                    if pb and pb > 0:
                        pb_values.append(round(pb, 2))

        except Exception as e:
            error_msg = str(e)
            if '权限' not in error_msg:
                print(f"获取历史PB失败 {ts_code}: {e}")

        return pb_values

    def _analyze_pb(self, pb_values: List[float]) -> Optional[Dict]:
        """分析PB数据并计算推荐阈值 - 与 stock_analyzer.py 保持一致"""
        if len(pb_values) < 50:  # 至少需要50个数据点
            return None

        sorted_pbs = sorted(pb_values)
        n = len(sorted_pbs)

        min_pb = sorted_pbs[0]
        max_pb = sorted_pbs[-1]
        avg_pb = sum(sorted_pbs) / n
        median_pb = sorted_pbs[n // 2]

        # 计算分位数 - 与 stock_analyzer.py 保持一致
        percentile_10 = sorted_pbs[int(n * 0.10)]
        percentile_15 = sorted_pbs[int(n * 0.15)]
        percentile_75 = sorted_pbs[int(n * 0.75)]

        # 推荐阈值 - 与 stock_analyzer.py 保持一致
        recommended_buy_pb = round(percentile_15, 2)   # 请客价: 15%分位 (更严格)
        recommended_add_pb = round(percentile_10, 2)   # 加仓价: 10%分位
        recommended_sell_pb = round(percentile_75, 2)  # 退出价: 75%分位

        return {
            'min_pb': round(min_pb, 2),
            'max_pb': round(max_pb, 2),
            'avg_pb': round(avg_pb, 2),
            'median_pb': round(median_pb, 2),
            'recommended_buy_pb': recommended_buy_pb,
            'recommended_add_pb': recommended_add_pb,
            'recommended_sell_pb': recommended_sell_pb,
            'percentile_10': round(percentile_10, 2),
            'percentile_15': round(percentile_15, 2),
            'percentile_75': round(percentile_75, 2)
        }

    def scan_stocks(self, max_distance_pct: float = 20.0, limit: int = 10,
                    progress_callback=None) -> List[StockRecommendation]:
        """
        扫描股票池，寻找PB接近请客价的股票

        Args:
            max_distance_pct: 距离请客价的最大百分比（默认20%）
            limit: 返回的最大股票数量
            progress_callback: 进度回调函数 callback(current, total, message)

        Returns:
            股票推荐列表，按距离请客价百分比排序

        注意：此功能需要 Tushare 120+ 积分权限访问 daily_basic 接口
        """
        if not self._pro:
            print("Tushare API 未初始化，无法扫描股票")
            return []

        recommendations = []
        total = len(self.STOCK_UNIVERSE)

        for idx, code in enumerate(self.STOCK_UNIVERSE):
            if progress_callback:
                progress_callback(idx + 1, total, f"正在分析 {code}...")

            # 获取股票基本数据
            stock_data = self._fetch_stock_data(code)
            if not stock_data:
                continue

            # 获取历史PB
            ts_code = self._get_ts_code(code)
            pb_values = self._fetch_pb_history(ts_code)

            # 分析PB
            pb_analysis = self._analyze_pb(pb_values)
            if not pb_analysis:
                continue

            current_pb = stock_data['current_pb']
            recommended_buy_pb = pb_analysis['recommended_buy_pb']

            # 计算距离请客价的百分比
            if recommended_buy_pb > 0:
                distance_pct = ((current_pb - recommended_buy_pb) / recommended_buy_pb) * 100
            else:
                continue

            # 筛选：当前PB在请客价的±max_distance_pct%范围内
            if distance_pct <= max_distance_pct:
                recommendations.append(StockRecommendation(
                    code=stock_data['code'],
                    name=stock_data['name'],
                    industry=stock_data['industry'],
                    current_price=stock_data['price'],
                    current_pb=current_pb,
                    recommended_buy_pb=recommended_buy_pb,
                    pb_distance_pct=round(distance_pct, 2),
                    min_pb=pb_analysis['min_pb'],
                    max_pb=pb_analysis['max_pb'],
                    avg_pb=pb_analysis['avg_pb'],
                    market_cap=stock_data['market_cap'],
                    pe_ttm=stock_data['pe_ttm'],
                    roe=None  # 暂不获取ROE
                ))

        # 按距离请客价百分比排序（越低越好）
        recommendations.sort(key=lambda x: x.pb_distance_pct)

        return recommendations[:limit]

    def quick_scan(self, progress_callback=None) -> List[StockRecommendation]:
        """
        快速扫描：使用默认参数（20%距离，返回10只）
        """
        return self.scan_stocks(
            max_distance_pct=20.0,
            limit=10,
            progress_callback=progress_callback
        )
