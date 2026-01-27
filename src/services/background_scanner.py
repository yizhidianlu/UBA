"""Background stock scanner service for smart stock selection."""
import time
import threading
import json
import os
from datetime import datetime
from typing import Optional, List, Callable
import requests
from .http_utils import HTTPClient

try:
    import tushare as ts
    TUSHARE_AVAILABLE = True
except ImportError:
    ts = None
    TUSHARE_AVAILABLE = False

from src.database import get_session, init_db
from src.database.models import StockCandidate, ScanProgress, CandidateStatus, Asset
from src.services.ai_analyzer import AIAnalyzer, get_qwen_api_key

# 缓存文件路径
CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data')
STOCK_LIST_CACHE = os.path.join(CACHE_DIR, 'stock_list_cache.json')


class BackgroundScanner:
    """后台股票扫描器 - 自动扫描A股寻找低估股票"""

    def __init__(self, user_id: int, enable_ai_scoring: bool = True):
        # 使用统一的HTTP客户端
        self.http_client = HTTPClient(timeout=30, max_retries=3)
        self.http_client.session.headers.update({
            'Referer': 'https://quote.eastmoney.com/'
        })
        self.session = self.http_client.session  # 保留兼容性
        self.user_id = user_id
        self._stop_event = threading.Event()
        self._scan_thread: Optional[threading.Thread] = None
        self._progress_callback: Optional[Callable] = None
        self._cached_stocks: Optional[List[dict]] = None
        self._enable_ai_scoring = enable_ai_scoring
        self._ai_analyzer: Optional[AIAnalyzer] = None
        # AI评分独立线程
        self._ai_stop_event = threading.Event()
        self._ai_thread: Optional[threading.Thread] = None
        self._ai_scoring_interval = 30  # AI评分间隔(秒)

    def _get_ai_analyzer(self) -> Optional[AIAnalyzer]:
        """获取 AI 分析器实例（延迟初始化）"""
        if not self._enable_ai_scoring:
            return None
        if self._ai_analyzer is None:
            api_key = get_qwen_api_key()
            if api_key:
                self._ai_analyzer = AIAnalyzer(api_key)
            else:
                print("未配置 Qwen API Key，AI 评分功能已禁用")
        return self._ai_analyzer

    def get_ai_score(self, code: str, name: str = None) -> Optional[dict]:
        """获取股票的 AI 评分"""
        analyzer = self._get_ai_analyzer()
        if not analyzer:
            return None

        try:
            # 获取基本面数据
            fundamental = analyzer.fetch_fundamental_data(code)
            if not fundamental:
                print(f"  无法获取 {code} 基本面数据")
                return None

            # 生成 AI 分析报告
            report = analyzer.generate_analysis_report(fundamental)
            if report:
                return {
                    'ai_score': report.ai_score,
                    'ai_suggestion': report.summary
                }
            else:
                print(f"  AI 分析失败: {analyzer.last_error}")
                return None

        except Exception as e:
            print(f"  获取 AI 评分失败 {code}: {e}")
            return None

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
        return self.http_client.get(url, params=params, timeout=30)

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

            # 计算统计数据 - 与 stock_analyzer.py 保持一致
            sorted_pbs = sorted(pb_values)
            n = len(sorted_pbs)
            min_pb = sorted_pbs[0]
            max_pb = sorted_pbs[-1]
            avg_pb = sum(sorted_pbs) / n
            median_pb = sorted_pbs[n // 2]
            current_pb = current_price / bvps if current_price else sorted_pbs[-1]

            # 计算分位数 - 与 stock_analyzer.py 保持一致
            percentile_10 = sorted_pbs[int(n * 0.10)]
            percentile_15 = sorted_pbs[int(n * 0.15)]
            percentile_75 = sorted_pbs[int(n * 0.75)]

            # 推荐阈值 - 与 stock_analyzer.py 保持一致
            recommended_buy_pb = round(percentile_15, 2)   # 请客价: 15%分位 (更严格)
            recommended_add_pb = round(percentile_10, 2)   # 加仓价: 10%分位
            recommended_sell_pb = round(percentile_75, 2)  # 退出价: 75%分位

            # 计算距离请客价的百分比
            pb_distance_pct = ((current_pb - recommended_buy_pb) / recommended_buy_pb) * 100

            return {
                'code': ts_code,
                'name': name,
                'industry': industry,
                'current_price': current_price,
                'current_pb': round(current_pb, 2),
                'recommended_buy_pb': recommended_buy_pb,
                'recommended_add_pb': recommended_add_pb,
                'recommended_sell_pb': recommended_sell_pb,
                'pb_distance_pct': round(pb_distance_pct, 1),
                'min_pb': round(min_pb, 2),
                'max_pb': round(max_pb, 2),
                'avg_pb': round(avg_pb, 2),
                'median_pb': round(median_pb, 2),
                'percentile_10': round(percentile_10, 2),
                'percentile_15': round(percentile_15, 2),
                'percentile_75': round(percentile_75, 2)
            }

        except Exception as e:
            print(f"分析股票 {code} 失败: {e}")
            return None

    def start_scan(self, pb_threshold_pct: float = 20.0, scan_interval: int = 120,
                   progress_callback: Callable = None):
        """启动后台扫描"""
        # 检查是否已有线程在运行
        if self._scan_thread and self._scan_thread.is_alive():
            print("扫描已在运行中")
            return False

        # 检查数据库中的运行状态（防止多实例启动）
        init_db()
        db_session = get_session()
        try:
            progress = db_session.query(ScanProgress).filter(
                ScanProgress.user_id == self.user_id
            ).first()
            if progress and progress.is_running:
                print("数据库显示扫描正在运行中，请先停止旧的扫描任务")
                return False
        finally:
            db_session.close()

        self._stop_event.clear()
        self._progress_callback = progress_callback
        self._scan_thread = threading.Thread(
            target=self._scan_loop,
            args=(pb_threshold_pct, scan_interval),
            daemon=True
        )
        self._scan_thread.start()
        print(f"后台扫描已启动 (用户ID: {self.user_id})")
        return True

    def stop_scan(self):
        """停止后台扫描"""
        self._stop_event.set()
        if self._scan_thread:
            self._scan_thread.join(timeout=5)

        # 清理数据库状态
        init_db()
        db_session = get_session()
        try:
            progress = db_session.query(ScanProgress).filter(
                ScanProgress.user_id == self.user_id
            ).first()
            if progress:
                progress.is_running = False
                progress.updated_at = datetime.now()
                db_session.commit()
        finally:
            db_session.close()

        print(f"后台扫描已停止 (用户ID: {self.user_id})")

    def is_running(self) -> bool:
        """检查扫描是否在运行"""
        return self._scan_thread is not None and self._scan_thread.is_alive()

    def reset_scan_status(self):
        """重置扫描状态（用于清理异常状态）"""
        init_db()
        db_session = get_session()
        try:
            progress = db_session.query(ScanProgress).filter(
                ScanProgress.user_id == self.user_id
            ).first()
            if progress:
                progress.is_running = False
                progress.updated_at = datetime.now()
                db_session.commit()
                print(f"扫描状态已重置 (用户ID: {self.user_id})")
                return True
        except Exception as e:
            print(f"重置扫描状态失败: {e}")
        finally:
            db_session.close()
        return False

    def _scan_loop(self, pb_threshold_pct: float, scan_interval: int):
        """扫描主循环"""
        init_db()
        db_session = get_session()
        progress = None

        try:
            # 获取或创建扫描进度
            progress = db_session.query(ScanProgress).filter(
                ScanProgress.user_id == self.user_id
            ).first()
            if not progress:
                progress = ScanProgress(
                    user_id=self.user_id,
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
            existing_codes = set(
                a.code for a in db_session.query(Asset.code).filter(
                    Asset.user_id == self.user_id
                ).all()
            )

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
                    StockCandidate.status == CandidateStatus.PENDING,
                    StockCandidate.user_id == self.user_id
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
                        print(f"  [OK] 符合条件! 距离请客价: {analysis['pb_distance_pct']:.1f}%")

                        # 获取 AI 评分
                        ai_score = None
                        ai_suggestion = None
                        if self._enable_ai_scoring:
                            print(f"  正在获取 AI 评分...")
                            ai_result = self.get_ai_score(analysis['code'], analysis['name'])
                            if ai_result:
                                ai_score = ai_result['ai_score']
                                ai_suggestion = ai_result['ai_suggestion']
                                print(f"  AI评分: {ai_score}分")

                        # 添加到备选池
                        candidate = StockCandidate(
                            user_id=self.user_id,
                            code=analysis['code'],
                            name=analysis['name'],
                            industry=analysis['industry'],
                            current_price=analysis['current_price'],
                            current_pb=analysis['current_pb'],
                            recommended_buy_pb=analysis['recommended_buy_pb'],
                            recommended_add_pb=analysis.get('recommended_add_pb'),
                            recommended_sell_pb=analysis.get('recommended_sell_pb'),
                            pb_distance_pct=analysis['pb_distance_pct'],
                            min_pb=analysis['min_pb'],
                            max_pb=analysis['max_pb'],
                            avg_pb=analysis['avg_pb'],
                            pe_ttm=stock.get('pe'),
                            market_cap=stock.get('market_cap'),
                            ai_score=ai_score,
                            ai_suggestion=ai_suggestion,
                            status=CandidateStatus.PENDING
                        )
                        db_session.add(candidate)
                        if self._enable_ai_scoring:
                            self.ensure_ai_scoring_running()

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
            progress = db_session.query(ScanProgress).filter(
                ScanProgress.user_id == self.user_id
            ).first()
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
            query = db_session.query(StockCandidate).filter(
                StockCandidate.user_id == self.user_id
            )
            if status:
                query = query.filter(StockCandidate.status == status)
            candidates = query.order_by(StockCandidate.pb_distance_pct).all()
            if self._enable_ai_scoring and (status is None or status == CandidateStatus.PENDING):
                has_unscored = any(
                    candidate.ai_score in (None, 0)
                    for candidate in candidates
                    if candidate.status == CandidateStatus.PENDING
                )
                if has_unscored:
                    self.ensure_ai_scoring_running()
            return candidates
        finally:
            db_session.close()

    def update_candidate_status(self, candidate_id: int, status: CandidateStatus):
        """更新备选股票状态"""
        db_session = get_session()
        try:
            candidate = db_session.query(StockCandidate).filter(
                StockCandidate.id == candidate_id,
                StockCandidate.user_id == self.user_id
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
            query = db_session.query(StockCandidate).filter(
                StockCandidate.user_id == self.user_id
            )
            if status:
                query = query.filter(StockCandidate.status == status)
            query.delete()
            db_session.commit()
        finally:
            db_session.close()

    # ==================== 独立AI评分线程 ====================

    def ensure_ai_scoring_running(self, interval: int = 30) -> bool:
        """确保AI评分线程在运行"""
        if not self._enable_ai_scoring:
            return False
        if self.is_ai_scoring_running():
            return True
        return self.start_ai_scoring(interval=interval)

    def start_ai_scoring(self, interval: int = 30):
        """启动独立的AI评分线程"""
        if self._ai_thread and self._ai_thread.is_alive():
            print("AI评分线程已在运行中")
            return False

        self._ai_stop_event.clear()
        self._ai_scoring_interval = interval
        self._ai_thread = threading.Thread(
            target=self._ai_scoring_loop,
            daemon=True
        )
        self._ai_thread.start()
        print("AI评分线程已启动")
        return True

    def stop_ai_scoring(self):
        """停止AI评分线程"""
        self._ai_stop_event.set()
        if self._ai_thread:
            self._ai_thread.join(timeout=5)
        print("AI评分线程已停止")

    def is_ai_scoring_running(self) -> bool:
        """检查AI评分线程是否在运行"""
        return self._ai_thread is not None and self._ai_thread.is_alive()

    def _ai_scoring_loop(self):
        """AI评分主循环 - 按添加时间从早到晚依次评分"""
        init_db()

        while not self._ai_stop_event.is_set():
            db_session = get_session()
            try:
                # 查找未评分的备选股票，按添加时间从早到晚排序
                unscored = db_session.query(StockCandidate).filter(
                    StockCandidate.status == CandidateStatus.PENDING,
                    StockCandidate.user_id == self.user_id,
                    (StockCandidate.ai_score == None) | (StockCandidate.ai_score == 0)
                ).order_by(StockCandidate.scanned_at.asc()).first()

                if unscored:
                    print(f"[AI评分] 正在评分: {unscored.name} ({unscored.code})")

                    # 获取AI评分
                    ai_result = self.get_ai_score(unscored.code, unscored.name)

                    if ai_result:
                        unscored.ai_score = ai_result['ai_score']
                        unscored.ai_suggestion = ai_result['ai_suggestion']
                        unscored.updated_at = datetime.now()
                        db_session.commit()
                        print(f"[AI评分] {unscored.name} 评分完成: {ai_result['ai_score']}分")
                    else:
                        # 标记为已尝试评分（设为-1表示评分失败）
                        unscored.ai_score = -1
                        unscored.updated_at = datetime.now()
                        db_session.commit()
                        print(f"[AI评分] {unscored.name} 评分失败")

            except Exception as e:
                print(f"[AI评分] 评分出错: {e}")
            finally:
                db_session.close()

            # 等待间隔
            for _ in range(self._ai_scoring_interval):
                if self._ai_stop_event.is_set():
                    break
                time.sleep(1)

        print("[AI评分] 线程已退出")


# 全局扫描器实例
_scanner_instance: dict[int, BackgroundScanner] = {}


def get_scanner(user_id: int) -> BackgroundScanner:
    """获取全局扫描器实例"""
    if user_id not in _scanner_instance:
        _scanner_instance[user_id] = BackgroundScanner(user_id)
    return _scanner_instance[user_id]
