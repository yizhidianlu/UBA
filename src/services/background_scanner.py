"""Background stock scanner service for smart stock selection."""
import time
import threading
import json
import os
from datetime import datetime
from typing import Optional, List, Callable
import requests

try:
    import tushare as ts
    TUSHARE_AVAILABLE = True
except ImportError:
    ts = None
    TUSHARE_AVAILABLE = False

from src.database import get_session, init_db
from src.database.models import StockCandidate, ScanProgress, CandidateStatus, Asset

# 缓存文件路径
CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data')
STOCK_LIST_CACHE = os.path.join(CACHE_DIR, 'stock_list_cache.json')


class BackgroundScanner:
    """后台股票扫描器 - 自动扫描A股寻找低估股票"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://quote.eastmoney.com/'
        })
        self._stop_event = threading.Event()
        self._scan_thread: Optional[threading.Thread] = None
        self._progress_callback: Optional[Callable] = None
        self._cached_stocks: Optional[List[dict]] = None

    def _load_stock_cache(self) -> Optional[List[dict]]:
        """从缓存加载股票列表"""
        try:
            if os.path.exists(STOCK_LIST_CACHE):
                with open(STOCK_LIST_CACHE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 检查缓存是否过期（24小时）
                    cache_time = datetime.fromisoformat(data.get('timestamp', '2000-01-01'))
                    if (datetime.now() - cache_time).total_seconds() < 86400:
                        print(f"从缓存加载股票列表: {len(data.get('stocks', []))} 只")
                        return data.get('stocks', [])
        except Exception as e:
            print(f"加载缓存失败: {e}")
        return None

    def _save_stock_cache(self, stocks: List[dict]):
        """保存股票列表到缓存"""
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(STOCK_LIST_CACHE, 'w', encoding='utf-8') as f:
                json.dump({
                    'timestamp': datetime.now().isoformat(),
                    'stocks': stocks
                }, f, ensure_ascii=False)
            print(f"股票列表已缓存: {len(stocks)} 只")
        except Exception as e:
            print(f"保存缓存失败: {e}")

    def _request_with_retry(self, url: str, params: dict, max_retries: int = 3) -> Optional[dict]:
        """带重试的HTTP请求"""
        for attempt in range(max_retries):
            try:
                resp = self.session.get(url, params=params, timeout=30)
                return resp.json()
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"请求失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                    time.sleep(2 ** attempt)  # 指数退避
                else:
                    print(f"请求失败，已重试 {max_retries} 次: {e}")
        return None

    def get_all_a_shares(self) -> List[dict]:
        """获取所有A股股票列表"""
        # 1. 先尝试从缓存加载
        cached = self._load_stock_cache()
        if cached:
            return cached

        stocks = []

        # 2. 尝试使用 Tushare
        if TUSHARE_AVAILABLE:
            try:
                print("使用Tushare获取股票列表...")
                df = ts.get_today_all()
                if df is not None and len(df) > 0:
                    for _, row in df.iterrows():
                        code = str(row.get('code', ''))
                        name = str(row.get('name', ''))
                        # 过滤ST股票和退市股
                        if code and name and 'ST' not in name and '退' not in name:
                            stocks.append({
                                'code': code,
                                'name': name,
                                'change_pct': row.get('changepercent'),
                                'price': row.get('trade'),
                                'pb': row.get('pb'),
                                'pe': row.get('pe'),
                                'market_cap': row.get('mktcap') / 10000 if row.get('mktcap') else None,  # 转换为亿
                                'industry': ''
                            })
                    print(f"Tushare获取成功: {len(stocks)} 只股票")
                    self._save_stock_cache(stocks)
                    return stocks
            except Exception as e:
                print(f"Tushare获取失败: {e}")

        # 备用: 使用东方财富接口
        print("使用东方财富接口获取股票列表...")
        try:
            url = "https://push2.eastmoney.com/api/qt/clist/get"
            page_size = 100

            for fs in ["m:1+t:2,m:1+t:23", "m:0+t:6,m:0+t:80"]:
                page = 1
                while True:
                    params = {
                        'pn': page,
                        'pz': page_size,
                        'fs': fs,
                        'fields': 'f12,f14,f3,f2,f23,f9,f20,f100',
                        'ut': 'fa5fd1943c7b386f172d6893dbfba10b'
                    }
                    data = self._request_with_retry(url, params)
                    if not data:
                        break

                    diff = data.get('data', {}).get('diff')
                    if not diff:
                        break

                    items = diff.values() if isinstance(diff, dict) else diff
                    items_list = list(items)

                    if not items_list:
                        break

                    for item in items_list:
                        code = item.get('f12', '')
                        name = item.get('f14', '')
                        if code and name and 'ST' not in name and '退' not in name:
                            stocks.append({
                                'code': code,
                                'name': name,
                                'change_pct': item.get('f3'),
                                'price': item.get('f2') / 100 if item.get('f2') else None,
                                'pb': item.get('f23') / 100 if item.get('f23') else None,
                                'pe': item.get('f9') / 100 if item.get('f9') else None,
                                'market_cap': item.get('f20') / 100000000 if item.get('f20') else None,
                                'industry': item.get('f100', '')
                            })

                    if len(items_list) < page_size:
                        break

                    page += 1
                    time.sleep(0.5)

            # 保存到缓存
            if stocks:
                self._save_stock_cache(stocks)

        except Exception as e:
            print(f"东方财富获取失败: {e}")

        return stocks

    def analyze_stock_pb(self, code: str, years: int = 5) -> Optional[dict]:
        """分析单只股票的PB历史"""
        try:
            # 确定市场
            if code.startswith('6'):
                ts_code = f"{code}.SH"
                secid = f"1.{code}"
            else:
                ts_code = f"{code}.SZ"
                secid = f"0.{code}"

            # 获取当前每股净资产
            url = 'https://push2.eastmoney.com/api/qt/stock/get'
            params = {
                'secid': secid,
                'fields': 'f43,f57,f58,f92,f127',
                'ut': 'fa5fd1943c7b386f172d6893dbfba10b'
            }
            resp = self.session.get(url, params=params, timeout=10)
            data = resp.json()

            if not data.get('data'):
                return None

            info = data['data']
            bvps = info.get('f92')
            if not bvps or bvps <= 0:
                return None

            current_price = info.get('f43', 0) / 100 if info.get('f43') else None
            name = info.get('f58', '')
            industry = info.get('f127', '')

            # 获取历史K线计算PB
            days = years * 250
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

            pb_values = []
            if kline_data.get('data', {}).get('klines'):
                for kline in kline_data['data']['klines']:
                    try:
                        parts = kline.split(',')
                        close = float(parts[2])
                        pb = close / bvps
                        if pb > 0:
                            pb_values.append(pb)
                    except:
                        continue

            if len(pb_values) < 50:
                return None

            # 计算统计数据
            sorted_pbs = sorted(pb_values)
            n = len(sorted_pbs)
            min_pb = sorted_pbs[0]
            max_pb = sorted_pbs[-1]
            avg_pb = sum(sorted_pbs) / n
            current_pb = current_price / bvps if current_price else sorted_pbs[-1]

            # 计算推荐请客价 (25%分位)
            recommended_buy_pb = sorted_pbs[int(n * 0.25)]

            # 计算距离请客价的百分比
            pb_distance_pct = ((current_pb - recommended_buy_pb) / recommended_buy_pb) * 100

            return {
                'code': ts_code,
                'name': name,
                'industry': industry,
                'current_price': current_price,
                'current_pb': round(current_pb, 2),
                'recommended_buy_pb': round(recommended_buy_pb, 2),
                'pb_distance_pct': round(pb_distance_pct, 1),
                'min_pb': round(min_pb, 2),
                'max_pb': round(max_pb, 2),
                'avg_pb': round(avg_pb, 2)
            }

        except Exception as e:
            print(f"分析股票 {code} 失败: {e}")
            return None

    def start_scan(self, pb_threshold_pct: float = 20.0, scan_interval: int = 120,
                   progress_callback: Callable = None):
        """启动后台扫描"""
        if self._scan_thread and self._scan_thread.is_alive():
            print("扫描已在运行中")
            return False

        self._stop_event.clear()
        self._progress_callback = progress_callback
        self._scan_thread = threading.Thread(
            target=self._scan_loop,
            args=(pb_threshold_pct, scan_interval),
            daemon=True
        )
        self._scan_thread.start()
        return True

    def stop_scan(self):
        """停止后台扫描"""
        self._stop_event.set()
        if self._scan_thread:
            self._scan_thread.join(timeout=5)

    def is_running(self) -> bool:
        """检查扫描是否在运行"""
        return self._scan_thread is not None and self._scan_thread.is_alive()

    def _scan_loop(self, pb_threshold_pct: float, scan_interval: int):
        """扫描主循环"""
        init_db()
        db_session = get_session()
        progress = None

        try:
            # 获取或创建扫描进度
            progress = db_session.query(ScanProgress).first()
            if not progress:
                progress = ScanProgress(
                    current_index=0,
                    is_running=True,
                    scan_interval=scan_interval,
                    pb_threshold_pct=pb_threshold_pct,
                    started_at=datetime.now()
                )
                db_session.add(progress)
            else:
                progress.is_running = True
                progress.scan_interval = scan_interval
                progress.pb_threshold_pct = pb_threshold_pct
                progress.started_at = datetime.now()
            db_session.commit()

            # 获取股票列表（带重试）
            print("正在获取A股列表...")
            stocks = None
            for attempt in range(3):
                stocks = self.get_all_a_shares()
                if stocks:
                    break
                print(f"获取股票列表失败，重试 {attempt + 1}/3...")
                time.sleep(5)

            if not stocks:
                print("获取股票列表失败，扫描终止")
                return

            progress.total_stocks = len(stocks)
            db_session.commit()
            print(f"共获取 {len(stocks)} 只股票")

            # 获取已在股票池中的股票
            existing_codes = set(a.code for a in db_session.query(Asset.code).all())

            # 从上次位置继续扫描
            start_index = progress.current_index

            for i in range(start_index, len(stocks)):
                if self._stop_event.is_set():
                    print("扫描已停止")
                    break

                stock = stocks[i]
                code = stock['code']

                # 跳过已在股票池的
                full_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
                if full_code in existing_codes:
                    progress.current_index = i + 1
                    progress.last_scanned_code = code
                    db_session.commit()
                    continue

                # 跳过已在备选池的
                existing_candidate = db_session.query(StockCandidate).filter(
                    StockCandidate.code == full_code,
                    StockCandidate.status == CandidateStatus.PENDING
                ).first()
                if existing_candidate:
                    progress.current_index = i + 1
                    progress.last_scanned_code = code
                    db_session.commit()
                    continue

                # 分析股票
                print(f"[{i+1}/{len(stocks)}] 分析 {stock['name']} ({code})...")
                analysis = self.analyze_stock_pb(code)

                if analysis:
                    # 检查是否符合条件
                    if analysis['pb_distance_pct'] <= pb_threshold_pct:
                        # 添加到备选池
                        candidate = StockCandidate(
                            code=analysis['code'],
                            name=analysis['name'],
                            industry=analysis['industry'],
                            current_price=analysis['current_price'],
                            current_pb=analysis['current_pb'],
                            recommended_buy_pb=analysis['recommended_buy_pb'],
                            pb_distance_pct=analysis['pb_distance_pct'],
                            min_pb=analysis['min_pb'],
                            max_pb=analysis['max_pb'],
                            avg_pb=analysis['avg_pb'],
                            pe_ttm=stock.get('pe'),
                            market_cap=stock.get('market_cap'),
                            status=CandidateStatus.PENDING
                        )
                        db_session.add(candidate)
                        print(f"  [OK] 符合条件! 距离请客价: {analysis['pb_distance_pct']:.1f}%")

                # 更新进度
                progress.current_index = i + 1
                progress.last_scanned_code = code
                progress.updated_at = datetime.now()
                db_session.commit()

                # 回调通知
                if self._progress_callback:
                    self._progress_callback(i + 1, len(stocks), stock['name'])

                # 等待间隔
                time.sleep(scan_interval)

            # 扫描完成，重置索引
            if not self._stop_event.is_set():
                progress.current_index = 0
                print("扫描完成一轮")

        except Exception as e:
            print(f"扫描出错: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if progress:
                progress.is_running = False
                db_session.commit()
            db_session.close()

    def get_progress(self) -> Optional[dict]:
        """获取当前扫描进度"""
        db_session = get_session()
        try:
            progress = db_session.query(ScanProgress).first()
            if progress:
                return {
                    'current_index': progress.current_index,
                    'total_stocks': progress.total_stocks,
                    'last_scanned_code': progress.last_scanned_code,
                    'is_running': progress.is_running,
                    'scan_interval': progress.scan_interval,
                    'pb_threshold_pct': progress.pb_threshold_pct,
                    'progress_pct': (progress.current_index / progress.total_stocks * 100) if progress.total_stocks > 0 else 0
                }
        finally:
            db_session.close()
        return None

    def get_candidates(self, status: CandidateStatus = None) -> List[StockCandidate]:
        """获取备选池股票"""
        db_session = get_session()
        try:
            query = db_session.query(StockCandidate)
            if status:
                query = query.filter(StockCandidate.status == status)
            return query.order_by(StockCandidate.pb_distance_pct).all()
        finally:
            db_session.close()

    def update_candidate_status(self, candidate_id: int, status: CandidateStatus):
        """更新备选股票状态"""
        db_session = get_session()
        try:
            candidate = db_session.query(StockCandidate).filter(
                StockCandidate.id == candidate_id
            ).first()
            if candidate:
                candidate.status = status
                candidate.updated_at = datetime.now()
                db_session.commit()
        finally:
            db_session.close()

    def clear_candidates(self, status: CandidateStatus = None):
        """清空备选池"""
        db_session = get_session()
        try:
            query = db_session.query(StockCandidate)
            if status:
                query = query.filter(StockCandidate.status == status)
            query.delete()
            db_session.commit()
        finally:
            db_session.close()


# 全局扫描器实例
_scanner_instance: Optional[BackgroundScanner] = None


def get_scanner() -> BackgroundScanner:
    """获取全局扫描器实例"""
    global _scanner_instance
    if _scanner_instance is None:
        _scanner_instance = BackgroundScanner()
    return _scanner_instance
