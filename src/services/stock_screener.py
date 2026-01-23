"""Stock screening service to find undervalued stocks based on PB."""
from typing import Optional, List, Dict
from dataclasses import dataclass
from datetime import datetime, timedelta
import requests
import time


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
    """股票筛选器：寻找PB接近请客价的股票"""

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
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://quote.eastmoney.com/'
        })

    def _get_secid(self, code: str) -> str:
        """转换股票代码为东财secid"""
        code = code.upper().replace('.SH', '').replace('.SZ', '')
        if code.startswith('6'):
            return f"1.{code}"
        else:
            return f"0.{code}"

    def _get_full_code(self, code: str) -> str:
        """获取完整股票代码"""
        code = code.upper().replace('.SH', '').replace('.SZ', '')
        if code.startswith('6'):
            return f"{code}.SH"
        else:
            return f"{code}.SZ"

    def _fetch_stock_data(self, code: str) -> Optional[Dict]:
        """获取单只股票的详细数据"""
        secid = self._get_secid(code)

        try:
            # 获取实时行情和基本指标
            url = 'https://push2.eastmoney.com/api/qt/stock/get'
            params = {
                'secid': secid,
                'fields': 'f43,f44,f45,f46,f57,f58,f92,f116,f127,f162,f167',
                'ut': 'fa5fd1943c7b386f172d6893dbfba10b'
            }
            resp = self.session.get(url, params=params, timeout=10)
            data = resp.json()

            if not data.get('data'):
                return None

            d = data['data']
            price = d.get('f43', 0) / 100 if d.get('f43') else None
            bvps = d.get('f92')

            if not price or not bvps or bvps <= 0:
                return None

            current_pb = round(price / bvps, 2)

            return {
                'code': self._get_full_code(code),
                'name': d.get('f58', ''),
                'industry': d.get('f127', ''),
                'price': price,
                'current_pb': current_pb,
                'bvps': bvps,
                'market_cap': d.get('f116') / 100000000 if d.get('f116') else None,
                'pe_ttm': d.get('f162') / 100 if d.get('f162') else None,
            }

        except Exception as e:
            print(f"获取股票数据失败 {code}: {e}")
            return None

    def _fetch_pb_history(self, code: str, secid: str, bvps: float, years: int = 3) -> List[float]:
        """获取历史PB数据"""
        pb_values = []

        try:
            days = years * 365
            kline_url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
            kline_params = {
                'secid': secid,
                'fields1': 'f1,f2,f3,f4,f5',
                'fields2': 'f51,f52,f53,f54,f55,f56,f57',
                'klt': '101',  # 日线
                'fqt': '0',    # 不复权
                'end': '20500101',
                'lmt': str(days),
                'ut': 'fa5fd1943c7b386f172d6893dbfba10b'
            }

            resp = self.session.get(kline_url, params=kline_params, timeout=15)
            kline_data = resp.json()

            if kline_data.get('data', {}).get('klines'):
                klines = kline_data['data']['klines']

                for kline in klines:
                    try:
                        parts = kline.split(',')
                        close = float(parts[2])
                        pb = round(close / bvps, 2)
                        if pb > 0:
                            pb_values.append(pb)
                    except Exception:
                        continue

        except Exception as e:
            print(f"获取历史PB失败 {code}: {e}")

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
        percentile_25 = sorted_pbs[int(n * 0.25)]
        percentile_75 = sorted_pbs[int(n * 0.75)]

        # 推荐阈值 - 与 stock_analyzer.py 保持一致
        recommended_buy_pb = round(percentile_25, 2)   # 请客价: 25%分位
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
            'percentile_25': round(percentile_25, 2),
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
        """
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
            secid = self._get_secid(code)
            pb_values = self._fetch_pb_history(code, secid, stock_data['bvps'])

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

            # 避免请求过于频繁
            time.sleep(0.1)

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
