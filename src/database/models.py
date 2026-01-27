"""Database models for the value investment trigger system."""
from datetime import datetime
from enum import Enum
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Date, Text,
    ForeignKey, Boolean, Enum as SQLEnum, UniqueConstraint, Index
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
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    code = Column(String(20), nullable=False)  # e.g., 600519.SH, 0700.HK
    name = Column(String(100), nullable=False)
    market = Column(SQLEnum(Market), nullable=False)
    industry = Column(String(100))
    tags = Column(String(500))  # comma-separated tags
    competence_score = Column(Integer, default=3)  # 1-5, 关注指数
    ai_score = Column(Integer)  # 0-100, AI投资评分
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
    __table_args__ = (
        UniqueConstraint("asset_id", "date", name="uq_valuation_asset_date"),
        Index("ix_valuation_asset_date", "asset_id", "date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    date = Column(Date, nullable=False)
    pb = Column(Float, nullable=False)
    price = Column(Float)  # 收盘价
    book_value_per_share = Column(Float)  # 每股净资产
    data_source = Column(String(50), default="akshare")  # 数据源: tushare, akshare, eastmoney
    pb_method = Column(String(50))  # PB计算方法: direct(直接获取), calculated(price/bvps计算)
    report_period = Column(String(20))  # 财报期: 如 2024Q3
    fetched_at = Column(DateTime, default=datetime.now)

    asset = relationship("Asset", back_populates="valuations")


class Portfolio(Base):
    """资金账户"""
    __tablename__ = "portfolios"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    name = Column(String(100), default="默认账户")
    total_asset = Column(Float, default=0)  # 总资产（NAV）
    cash = Column(Float, default=0)  # 现金余额
    market_value = Column(Float, default=0)  # 持仓市值
    frozen_cash = Column(Float, default=0)  # 冻结资金
    available_cash = Column(Float, default=0)  # 可用资金
    total_profit = Column(Float, default=0)  # 累计收益
    total_profit_rate = Column(Float, default=0)  # 累计收益率
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class PortfolioPosition(Base):
    """持仓信息"""
    __tablename__ = "portfolio_positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), unique=True, nullable=False)
    position_pct = Column(Float, default=0)  # 仓位百分比
    shares = Column(Integer, default=0)  # 持股数量
    avg_cost = Column(Float)  # 平均成本
    market_value = Column(Float)  # 持仓市值
    profit = Column(Float)  # 持仓盈亏
    profit_rate = Column(Float)  # 持仓盈亏率
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    asset = relationship("Asset", back_populates="position")


class Signal(Base):
    """触发信号"""
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
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
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    signal_id = Column(Integer, ForeignKey("signals.id"))
    action_date = Column(Date, nullable=False)
    action_type = Column(SQLEnum(ActionType), nullable=False)

    # 仓位信息
    planned_position_pct = Column(Float)  # 计划仓位百分比
    executed_position_pct = Column(Float)  # 实际仓位百分比

    # 交易信息
    shares = Column(Integer)  # 交易股数
    price = Column(Float)  # 成交价
    planned_amount = Column(Float)  # 计划交易金额
    executed_amount = Column(Float)  # 实际交易金额

    # 成本信息
    commission = Column(Float, default=0)  # 佣金
    stamp_duty = Column(Float, default=0)  # 印花税
    transfer_fee = Column(Float, default=0)  # 过户费
    total_cost = Column(Float, default=0)  # 总成本（含所有费用）

    # 决策信息
    reason = Column(Text, nullable=False)  # 必填：为什么符合规则
    emotion = Column(String(50))  # 可选：恐惧/贪婪/冲动等
    rule_compliance = Column(Boolean, default=True)  # 是否合规
    compliance_note = Column(Text)  # 合规说明

    # 订单信息（可选，对接实盘时使用）
    order_id = Column(String(100))  # 订单号
    order_status = Column(String(50))  # 订单状态

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
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    visit_date = Column(Date, nullable=False)
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
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
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
    ai_score = Column(Integer)          # AI投资评分 0-100
    ai_suggestion = Column(Text)        # AI投资建议摘要
    status = Column(SQLEnum(CandidateStatus), default=CandidateStatus.PENDING)
    scanned_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class ScanProgress(Base):
    """扫描进度记录"""
    __tablename__ = "scan_progress"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
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
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    code = Column(String(20), nullable=False, index=True)  # 股票代码
    name = Column(String(100), nullable=False)             # 股票名称
    summary = Column(Text)                                  # 一句话总结
    valuation_analysis = Column(Text)                       # 估值分析
    fundamental_analysis = Column(Text)                     # 基本面分析
    risk_analysis = Column(Text)                            # 风险分析
    investment_suggestion = Column(Text)                    # 投资建议
    pb_recommendation = Column(Text)                        # PB阈值建议
    full_report = Column(Text)                              # 完整报告
    ai_score = Column(Integer)                              # AI评分 0-100

    # 生成时的基本面数据快照
    price_at_report = Column(Float)                         # 报告时价格
    pb_at_report = Column(Float)                            # 报告时PB
    pe_at_report = Column(Float)                            # 报告时PE
    market_cap_at_report = Column(Float)                    # 报告时市值

    # 可审计字段（新增）
    input_data_json = Column(Text)                          # 输入数据快照（JSON格式）
    data_sources_json = Column(Text)                        # 数据来源映射（JSON格式）
    model_name = Column(String(100))                        # 使用的模型名称
    model_version = Column(String(50))                      # 模型版本
    prompt_tokens = Column(Integer)                         # prompt token数
    completion_tokens = Column(Integer)                     # completion token数
    total_tokens = Column(Integer)                          # 总token数
    estimated_cost = Column(Float)                          # 估算成本（美元）
    generation_time_ms = Column(Integer)                    # 生成耗时（毫秒）
    data_completeness_score = Column(Float)                 # 数据完整性评分 0-1
    missing_fields = Column(Text)                           # 缺失字段列表（逗号分隔）

    created_at = Column(DateTime, default=datetime.now)     # 报告生成时间
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class IndustryConfig(Base):
    """行业配置和默认阈值模板"""
    __tablename__ = "industry_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    industry_name = Column(String(100), unique=True, nullable=False)  # 行业名称
    display_name = Column(String(100))  # 显示名称
    description = Column(Text)  # 行业描述

    # 默认PB阈值
    default_buy_pb = Column(Float)  # 默认请客价
    default_add_pb = Column(Float)  # 默认加仓价
    default_sell_pb = Column(Float)  # 默认退出价

    # 行业特征
    typical_pb_range_min = Column(Float)  # 典型PB范围-最小
    typical_pb_range_max = Column(Float)  # 典型PB范围-最大
    typical_roe = Column(Float)  # 典型ROE
    cyclical = Column(Boolean, default=False)  # 是否周期性行业

    # 风控参数
    recommended_max_position = Column(Float)  # 建议最大仓位
    risk_level = Column(String(20))  # 风险等级：low/medium/high

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class User(Base):
    """账号信息"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    last_login_at = Column(DateTime)
