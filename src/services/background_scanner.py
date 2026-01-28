"""Background stock scanner service for smart stock selection."""
import time
import threading
import json
import os
from datetime import datetime, timedelta
from typing import Optional, List, Callable

try:
    import tushare as ts
    TUSHARE_AVAILABLE = True
except ImportError:
    ts = None
    TUSHARE_AVAILABLE = False

from src.database import get_session, init_db
from src.database.models import StockCandidate, ScanProgress, CandidateStatus, Asset
from src.services.ai_analyzer import AIAnalyzer, get_qwen_api_key
from src.services.stock_analyzer import _load_stock_basic_cache, _save_stock_basic_cache

# 缓存文件路径
CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data')
STOCK_LIST_CACHE = os.path.join(CACHE_DIR, 'stock_list_cache.json')


class BackgroundScanner:
    """后台股票扫描器 - 自动扫描A股寻找低估股票"""

    def __init__(self, user_id: int, enable_ai_scoring: bool = True):
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

    def get_all_a_shares(self) -> List[dict]:
        """获取所有A股股票列表"""
        # 1. 先尝试从缓存加载
        cached = self._load_stock_cache()
        if cached:
            return cached

        stocks = []

        # 只使用 Tushare
        if not TUSHARE_AVAILABLE:
            print("Tushare 未安装，无法获取股票列表")
            return stocks

        try:
            print("使用 Tushare 获取股票列表...")
            from src.services.stock_analyzer import get_tushare_token
            token = get_tushare_token()
            if not token:
                print("Tushare Token 未配置")
                return stocks

            ts.set_token(token)
            pro = ts.pro_api()

            # 获取所有A股列表
            df = pro.stock_basic(
                exchange='',
                list_status='L',
                fields='ts_code,symbol,name,area,industry,market'
            )

            if df is not None and len(df) > 0:
                for _, row in df.iterrows():
                    code = str(row.get('symbol', ''))
                    name = str(row.get('name', ''))
                    # 过滤ST股票和退市股
                    if code and name and 'ST' not in name and '退' not in name:
                        stocks.append({
                            'code': code,
                            'name': name,
                            'change_pct': None,  # Tushare stock_basic 不提供实时数据
                            'price': None,
                            'pb': None,
                            'pe': None,
                            'market_cap': None,
                            'industry': row.get('industry', '')
                        })
                print(f"Tushare 获取成功: {len(stocks)} 只股票")
                self._save_stock_cache(stocks)
                return stocks
        except Exception as e:
            print(f"Tushare 获取股票列表失败: {e}")
            import traceback
            traceback.print_exc()

        return stocks

    def analyze_stock_pb(self, code: str, years: int = 5) -> Optional[dict]:
        """分析单只股票的PB历史 - 使用 Tushare"""
        try:
            # 确定市场
            if code.startswith('6'):
                ts_code = f"{code}.SH"
            else:
                ts_code = f"{code}.SZ"

            # 初始化 Tushare
            if not TUSHARE_AVAILABLE:
                print(f"Tushare 未安装，无法分析 {code}")
                return None

            try:
                from src.services.stock_analyzer import get_tushare_token
                token = get_tushare_token()
                if not token:
                    print("Tushare Token 未配置")
                    return None

                ts.set_token(token)
                pro = ts.pro_api()
            except Exception as e:
                print(f"Tushare 初始化失败: {e}")
                return None

            # 获取股票基本信息 - 优先从缓存获取
            name = ''
            industry = ''

            # 从共享缓存获取
            stock_cache = _load_stock_basic_cache()
            if ts_code in stock_cache:
                name = stock_cache[ts_code].get('name', '')
                industry = stock_cache[ts_code].get('industry', '') or ''
            else:
                # 缓存中没有，调用API
                try:
                    time.sleep(0.5)  # 速率限制
                    basic_df = pro.stock_basic(ts_code=ts_code, fields='ts_code,name,industry')
                    if basic_df is None or basic_df.empty:
                        print(f"未找到股票信息: {ts_code}")
                        return None

                    name = basic_df.iloc[0]['name']
                    industry = basic_df.iloc[0]['industry'] if 'industry' in basic_df.columns else ''
                except Exception as e:
                    print(f"获取股票基本信息失败 {ts_code}: {e}")
                    return None

            # 获取历史 PB 数据
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=365 * years)).strftime('%Y%m%d')

            try:
                time.sleep(0.5)  # 速率限制
                df = pro.daily_basic(
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                    fields='trade_date,close,pb'
                )

                if df is None or df.empty:
                    print(f"未找到PB数据: {ts_code}")
                    return None

                # 过滤有效的 PB 数据
                df = df[df['pb'].notna() & (df['pb'] > 0)]
                if len(df) < 50:
                    print(f"PB数据不足: {ts_code}, 只有 {len(df)} 条")
                    return None

                pb_values = df['pb'].tolist()
                current_price = df.iloc[0]['close'] if 'close' in df.columns else None
                current_pb = df.iloc[0]['pb']

            except Exception as e:
                print(f"获取PB数据失败 {ts_code}: {e}")
                return None

            # 计算统计数据
            sorted_pbs = sorted(pb_values)
            n = len(sorted_pbs)
            min_pb = sorted_pbs[0]
            max_pb = sorted_pbs[-1]
            avg_pb = sum(sorted_pbs) / n
            median_pb = sorted_pbs[n // 2]

            # 计算分位数
            percentile_10 = sorted_pbs[int(n * 0.10)]
            percentile_15 = sorted_pbs[int(n * 0.15)]
            percentile_75 = sorted_pbs[int(n * 0.75)]

            # 推荐阈值
            recommended_buy_pb = round(percentile_15, 2)
            recommended_add_pb = round(percentile_10, 2)
            recommended_sell_pb = round(percentile_75, 2)

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
            import traceback
            traceback.print_exc()
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
