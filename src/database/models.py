"""Database models for the value investment trigger system."""
from datetime import datetime
from enum import Enum
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Date, Text,
    ForeignKey, Boolean, Enum as SQLEnum
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Market(str, Enum):
    A_SHARE = "A股"
    HK = "港股"
    US = "美股"


class SignalType(str, Enum):
    BUY = "BUY"
    ADD = "ADD"
    SELL = "SELL"


class SignalStatus(str, Enum):
    OPEN = "OPEN"
    DONE = "DONE"
    IGNORED = "IGNORED"


class ActionType(str, Enum):
    BUY = "BUY"
    ADD = "ADD"
    HOLD = "HOLD"
    SELL = "SELL"


class Asset(Base):
    """股票池中的股票"""
    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(20), unique=True, nullable=False)  # e.g., 600519.SH, 0700.HK
    name = Column(String(100), nullable=False)
    market = Column(SQLEnum(Market), nullable=False)
    industry = Column(String(100))
    tags = Column(String(500))  # comma-separated tags
    competence_score = Column(Integer, default=3)  # 1-5, 关注指数
    ai_score = Column(Integer)  # 1-5, AI投资评分
    ai_suggestion = Column(Text)  # AI投资建议摘要
    notes = Column(Text)  # 护城河/理解要点
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationships
    threshold = relationship("Threshold", back_populates="asset", uselist=False, cascade="all, delete-orphan")
    valuations = relationship("Valuation", back_populates="asset", cascade="all, delete-orphan")
    position = relationship("PortfolioPosition", back_populates="asset", uselist=False, cascade="all, delete-orphan")
    signals = relationship("Signal", back_populates="asset", cascade="all, delete-orphan")
    actions = relationship("Action", back_populates="asset", cascade="all, delete-orphan")


class Threshold(Base):
    """PB触发阈值配置"""
    __tablename__ = "thresholds"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), unique=True, nullable=False)
    buy_pb = Column(Float, nullable=False)  # 请客价
    add_pb = Column(Float)  # 压倒性优势价（可选）
    sell_pb = Column(Float)  # 目标价/退出价（可选）
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    asset = relationship("Asset", back_populates="threshold")


class Valuation(Base):
    """历史PB数据"""
    __tablename__ = "valuations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    date = Column(Date, nullable=False)
    pb = Column(Float, nullable=False)
    price = Column(Float)
    book_value_per_share = Column(Float)
    data_source = Column(String(50), default="akshare")
    fetched_at = Column(DateTime, default=datetime.now)

    asset = relationship("Asset", back_populates="valuations")

    class Meta:
        unique_together = ('asset_id', 'date')


class PortfolioPosition(Base):
    """持仓信息"""
    __tablename__ = "portfolio_positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), unique=True, nullable=False)
    position_pct = Column(Float, default=0)  # 仓位百分比
    shares = Column(Integer, default=0)  # 持股数量
    avg_cost = Column(Float)  # 平均成本
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    asset = relationship("Asset", back_populates="position")


class Signal(Base):
    """触发信号"""
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    date = Column(Date, nullable=False)
    signal_type = Column(SQLEnum(SignalType), nullable=False)
    pb = Column(Float, nullable=False)
    triggered_threshold = Column(Float, nullable=False)
    explanation = Column(Text)  # 可读解释
    status = Column(SQLEnum(SignalStatus), default=SignalStatus.OPEN)
    created_at = Column(DateTime, default=datetime.now)

    asset = relationship("Asset", back_populates="signals")


class Action(Base):
    """交易动作记录"""
    __tablename__ = "actions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    signal_id = Column(Integer, ForeignKey("signals.id"))
    action_date = Column(Date, nullable=False)
    action_type = Column(SQLEnum(ActionType), nullable=False)
    planned_position_pct = Column(Float)  # 计划仓位
    executed_position_pct = Column(Float)  # 实际仓位
    shares = Column(Integer)  # 交易股数
    price = Column(Float)  # 成交价
    reason = Column(Text, nullable=False)  # 必填：为什么符合规则
    emotion = Column(String(50))  # 可选：恐惧/贪婪/冲动等
    rule_compliance = Column(Boolean, default=True)  # 是否合规
    compliance_note = Column(Text)  # 合规说明
    created_at = Column(DateTime, default=datetime.now)

    asset = relationship("Asset", back_populates="actions")
    costs = relationship("Cost", back_populates="action", cascade="all, delete-orphan")


class Cost(Base):
    """交易成本"""
    __tablename__ = "costs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    action_id = Column(Integer, ForeignKey("actions.id"), nullable=False)
    fee = Column(Float, default=0)  # 手续费
    tax = Column(Float, default=0)  # 印花税
    slippage = Column(Float, default=0)  # 滑点

    action = relationship("Action", back_populates="costs")


class VisitLog(Base):
    """访问记录"""
    __tablename__ = "visit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    visit_date = Column(Date, nullable=False, unique=True)
    count = Column(Integer, default=1)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class CandidateStatus(str, Enum):
    PENDING = "PENDING"      # 待处理
    ADDED = "ADDED"          # 已加入股票池
    IGNORED = "IGNORED"      # 已忽略


class StockCandidate(Base):
    """智能选股备选池"""
    __tablename__ = "stock_candidates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(20), nullable=False)
    name = Column(String(100), nullable=False)
    industry = Column(String(100))
    current_price = Column(Float)
    current_pb = Column(Float)
    recommended_buy_pb = Column(Float)  # 推荐请客价
    recommended_add_pb = Column(Float)  # 推荐加仓价
    recommended_sell_pb = Column(Float) # 推荐退出价
    pb_distance_pct = Column(Float)     # 距离请客价百分比
    min_pb = Column(Float)
    max_pb = Column(Float)
    avg_pb = Column(Float)
    pe_ttm = Column(Float)
    market_cap = Column(Float)          # 市值(亿)
    ai_score = Column(Integer)          # AI投资评分 1-5
    ai_suggestion = Column(Text)        # AI投资建议摘要
    status = Column(SQLEnum(CandidateStatus), default=CandidateStatus.PENDING)
    scanned_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class ScanProgress(Base):
    """扫描进度记录"""
    __tablename__ = "scan_progress"

    id = Column(Integer, primary_key=True, autoincrement=True)
    current_index = Column(Integer, default=0)      # 当前扫描到的索引
    total_stocks = Column(Integer, default=0)       # 总股票数
    last_scanned_code = Column(String(20))          # 上次扫描的股票代码
    is_running = Column(Boolean, default=False)     # 是否正在运行
    scan_interval = Column(Integer, default=120)    # 扫描间隔(秒)
    pb_threshold_pct = Column(Float, default=20.0)  # PB距离阈值百分比
    started_at = Column(DateTime)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class AIAnalysisReport(Base):
    """AI分析报告存储"""
    __tablename__ = "ai_analysis_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(20), nullable=False, index=True)  # 股票代码
    name = Column(String(100), nullable=False)             # 股票名称
    summary = Column(Text)                                  # 一句话总结
    valuation_analysis = Column(Text)                       # 估值分析
    fundamental_analysis = Column(Text)                     # 基本面分析
    risk_analysis = Column(Text)                            # 风险分析
    investment_suggestion = Column(Text)                    # 投资建议
    pb_recommendation = Column(Text)                        # PB阈值建议
    full_report = Column(Text)                              # 完整报告
    ai_score = Column(Integer)                              # AI评分 1-5
    # 生成时的基本面数据快照
    price_at_report = Column(Float)                         # 报告时价格
    pb_at_report = Column(Float)                            # 报告时PB
    pe_at_report = Column(Float)                            # 报告时PE
    market_cap_at_report = Column(Float)                    # 报告时市值
    created_at = Column(DateTime, default=datetime.now)     # 报告生成时间
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class User(Base):
    """账号信息"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    last_login_at = Column(DateTime)
