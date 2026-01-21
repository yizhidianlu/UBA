"""Stock analysis service using Tushare for PB data and EastMoney for stock info."""
from typing import Optional, Tuple, List
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import requests

# Try to import tushare
try:
    import tushare as ts
    TUSHARE_AVAILABLE = True
except ImportError:
    TUSHARE_AVAILABLE = False

# Tushare Token
TUSHARE_TOKEN = "b49f13cb0fda07acdb4766d9bb8d8e63bc887607428fbe6acac2dcc9"


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
    percentile_25: float
    percentile_10: float
    data_count: int
    data_years: float
    recommended_buy_pb: float
    recommended_add_pb: float
    recommended_sell_pb: float
    pb_history: list


class StockAnalyzer:
    """股票分析器：混合使用东方财富和Tushare"""

    def __init__(self, token: str = TUSHARE_TOKEN):
        # HTTP session for EastMoney
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://quote.eastmoney.com/'
        })

        # Tushare API
        self.pro = None
        if TUSHARE_AVAILABLE:
            try:
                ts.set_token(token)
                self.pro = ts.pro_api()
            except Exception as e:
                print(f"Tushare初始化失败: {e}")

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
        """使用东方财富获取股票基本信息"""
        ts_code, market, secid = self.parse_code(code)

        try:
            url = 'https://push2.eastmoney.com/api/qt/stock/get'
            params = {
                'secid': secid,
                'fields': 'f57,f58,f127',
                'ut': 'fa5fd1943c7b386f172d6893dbfba10b'
            }
            resp = self.session.get(url, params=params, timeout=10)
            data = resp.json()

            if data.get('data'):
                info = data['data']
                name = info.get('f58', '')
                industry = info.get('f127', '')

                if name:
                    return StockInfo(
                        code=ts_code,
                        name=name,
                        industry=industry if industry else "",
                        market=market
                    )
        except Exception as e:
            print(f"获取股票信息失败: {e}")

        return None

    def fetch_pb_history(self, code: str, years: int = 5) -> List[dict]:
        """获取历史PB数据 - 优先使用Tushare，备用东方财富"""
        ts_code, market, secid = self.parse_code(code)
        pb_data = []

        # 尝试 Tushare
        if self.pro and market == "A股":
            pb_data = self._fetch_pb_tushare(ts_code, years)

        # 如果 Tushare 失败，使用东方财富备用方案
        if not pb_data:
            pb_data = self._fetch_pb_eastmoney(secid, years)

        return pb_data

    def _fetch_pb_tushare(self, ts_code: str, years: int) -> List[dict]:
        """使用Tushare获取PB数据"""
        pb_data = []

        try:
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
                                'price': float(row['close']) if row.get('close') else None
                            })
                    except Exception:
                        continue

        except Exception as e:
            print(f"Tushare获取PB失败: {e}")

        return pb_data

    def _fetch_pb_eastmoney(self, secid: str, years: int) -> List[dict]:
        """使用东方财富获取PB数据（备用方案）"""
        pb_data = []

        try:
            # 获取当前每股净资产
            url = 'https://push2.eastmoney.com/api/qt/stock/get'
            params = {
                'secid': secid,
                'fields': 'f43,f92',
                'ut': 'fa5fd1943c7b386f172d6893dbfba10b'
            }
            resp = self.session.get(url, params=params, timeout=10)
            data = resp.json()

            if not data.get('data'):
                return pb_data

            info = data['data']
            price_cents = info.get('f43')
            bvps = info.get('f92')

            if not bvps or bvps <= 0:
                return pb_data

            # 获取历史K线
            days = years * 365
            kline_url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
            kline_params = {
                'secid': secid,
                'fields1': 'f1,f2,f3,f4,f5',
                'fields2': 'f51,f52,f53,f54,f55,f56,f57',
                'klt': '101',
                'fqt': '0',
                'end': '20500101',
                'lmt': str(days),
                'ut': 'fa5fd1943c7b386f172d6893dbfba10b'
            }

            resp = self.session.get(kline_url, params=kline_params, timeout=30)
            kline_data = resp.json()

            if kline_data.get('data', {}).get('klines'):
                klines = kline_data['data']['klines']

                for kline in klines:
                    try:
                        parts = kline.split(',')
                        date_str = parts[0]
                        close = float(parts[2])
                        pb = round(close / bvps, 2)

                        if pb > 0:
                            pb_data.append({
                                'date': date.fromisoformat(date_str),
                                'pb': pb,
                                'price': close
                            })
                    except Exception:
                        continue

                pb_data.sort(key=lambda x: x['date'], reverse=True)

        except Exception as e:
            print(f"东方财富获取PB失败: {e}")

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
        percentile_25 = sorted_pbs[int(n * 0.25)]
        percentile_75 = sorted_pbs[int(n * 0.75)]

        recommended_buy_pb = round(percentile_25, 2)
        recommended_add_pb = round(percentile_10, 2)
        recommended_sell_pb = round(percentile_75, 2)

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
            percentile_25=round(percentile_25, 2),
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


