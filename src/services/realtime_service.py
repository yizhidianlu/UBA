"""Real-time data fetching service."""
from typing import Optional, Dict, List
from datetime import datetime, date
from dataclasses import dataclass
import requests


@dataclass
class RealtimeQuote:
    """实时行情数据"""
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
    """实时数据服务"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://quote.eastmoney.com/'
        })
        self._cache: Dict[str, RealtimeQuote] = {}
        self._cache_time: Optional[datetime] = None

    def _get_secid(self, code: str) -> str:
        """转换股票代码为东财secid"""
        code = code.upper()
        if '.SH' in code:
            pure = code.replace('.SH', '')
            return f"1.{pure}"
        elif '.SZ' in code:
            pure = code.replace('.SZ', '')
            return f"0.{pure}"
        elif '.HK' in code:
            pure = code.replace('.HK', '').zfill(5)
            return f"116.{pure}"
        elif code.startswith('6'):
            return f"1.{code}"
        elif code.startswith(('0', '3')):
            return f"0.{code}"
        else:
            return f"1.{code}"

    def get_realtime_quote(self, code: str) -> Optional[RealtimeQuote]:
        """获取单只股票实时行情"""
        secid = self._get_secid(code)

        try:
            url = 'https://push2.eastmoney.com/api/qt/stock/get'
            params = {
                'secid': secid,
                'fields': 'f43,f44,f45,f46,f47,f48,f50,f51,f52,f57,f58,f60,f92,f168,f169,f170',
                'ut': 'fa5fd1943c7b386f172d6893dbfba10b'
            }
            resp = self.session.get(url, params=params, timeout=5)
            data = resp.json()

            if data.get('data'):
                d = data['data']
                price = d.get('f43', 0) / 100 if d.get('f43') else 0
                prev_close = d.get('f60', 0) / 100 if d.get('f60') else 0
                bvps = d.get('f92')

                # 计算PB
                pb = round(price / bvps, 2) if bvps and bvps > 0 and price > 0 else None

                return RealtimeQuote(
                    code=code.upper(),
                    name=d.get('f58', ''),
                    price=price,
                    change=(d.get('f169', 0) / 100) if d.get('f169') else 0,
                    change_pct=(d.get('f170', 0) / 100) if d.get('f170') else 0,
                    pb=pb,
                    pe=d.get('f50') / 100 if d.get('f50') else None,
                    volume=d.get('f47', 0),
                    amount=d.get('f48', 0),
                    high=d.get('f44', 0) / 100 if d.get('f44') else 0,
                    low=d.get('f45', 0) / 100 if d.get('f45') else 0,
                    open=d.get('f46', 0) / 100 if d.get('f46') else 0,
                    prev_close=prev_close,
                    update_time=datetime.now()
                )
        except Exception as e:
            print(f"获取实时行情失败 {code}: {e}")

        return None

    def get_batch_quotes(self, codes: List[str]) -> Dict[str, RealtimeQuote]:
        """批量获取实时行情"""
        results = {}

        # 构建批量请求
        secids = [self._get_secid(code) for code in codes]

        try:
            url = 'https://push2.eastmoney.com/api/qt/ulist.np/get'
            params = {
                'secids': ','.join(secids),
                'fields': 'f12,f13,f14,f2,f3,f4,f5,f6,f7,f15,f16,f17,f18,f23',
                'ut': 'fa5fd1943c7b386f172d6893dbfba10b'
            }
            resp = self.session.get(url, params=params, timeout=10)
            data = resp.json()

            if data.get('data', {}).get('diff'):
                for item in data['data']['diff']:
                    try:
                        # f12=代码, f13=市场, f14=名称
                        code_num = item.get('f12', '')
                        market = item.get('f13', '')

                        if market == 0:
                            full_code = f"{code_num}.SZ"
                        elif market == 1:
                            full_code = f"{code_num}.SH"
                        else:
                            full_code = f"{code_num}.HK"

                        price = item.get('f2', 0) / 100 if item.get('f2') else 0
                        pb = item.get('f23', 0) / 100 if item.get('f23') else None

                        results[full_code] = RealtimeQuote(
                            code=full_code,
                            name=item.get('f14', ''),
                            price=price,
                            change=item.get('f4', 0) / 100 if item.get('f4') else 0,
                            change_pct=item.get('f3', 0) / 100 if item.get('f3') else 0,
                            pb=pb,
                            pe=None,
                            volume=item.get('f5', 0),
                            amount=item.get('f6', 0),
                            high=item.get('f15', 0) / 100 if item.get('f15') else 0,
                            low=item.get('f16', 0) / 100 if item.get('f16') else 0,
                            open=item.get('f17', 0) / 100 if item.get('f17') else 0,
                            prev_close=item.get('f18', 0) / 100 if item.get('f18') else 0,
                            update_time=datetime.now()
                        )
                    except Exception:
                        continue

        except Exception as e:
            print(f"批量获取行情失败: {e}")
            # 降级为逐个获取
            for code in codes:
                quote = self.get_realtime_quote(code)
                if quote:
                    results[quote.code] = quote

        self._cache = results
        self._cache_time = datetime.now()

        return results

    def get_cached_quotes(self) -> Dict[str, RealtimeQuote]:
        """获取缓存的行情数据"""
        return self._cache

    def get_cache_time(self) -> Optional[datetime]:
        """获取缓存更新时间"""
        return self._cache_time
