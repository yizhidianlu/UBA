"""
Streamlit缓存工具
提供统一的缓存策略，减少重复请求和计算
"""
import streamlit as st
from functools import wraps
from typing import Callable, Any
import hashlib
import json


# 缓存配置常量
TTL_REALTIME_QUOTE = 10  # 实时行情缓存：10秒
TTL_HISTORICAL_DATA = 3600  # 历史数据缓存：1小时
TTL_STOCK_INFO = 86400  # 股票基本信息缓存：1天
TTL_AI_REPORT = 604800  # AI报告缓存：7天


def cache_realtime_quote(func: Callable) -> Callable:
    """
    缓存实时行情数据

    使用 st.cache_data，TTL=10秒
    适用于：实时价格、实时PB等频繁变化的数据
    """
    return st.cache_data(ttl=TTL_REALTIME_QUOTE, show_spinner=False)(func)


def cache_historical_data(func: Callable) -> Callable:
    """
    缓存历史数据

    使用 st.cache_data，TTL=1小时
    适用于：历史PB数据、K线数据等
    """
    return st.cache_data(ttl=TTL_HISTORICAL_DATA, show_spinner=False)(func)


def cache_stock_info(func: Callable) -> Callable:
    """
    缓存股票基本信息

    使用 st.cache_data，TTL=1天
    适用于：股票名称、行业、市场等基本信息
    """
    return st.cache_data(ttl=TTL_STOCK_INFO, show_spinner=False)(func)


def cache_ai_report(func: Callable) -> Callable:
    """
    缓存AI报告

    使用 st.cache_data，TTL=7天
    适用于：AI分析报告等计算成本高的数据
    注意：AI报告应该主要从数据库读取，此缓存用于减少数据库查询
    """
    return st.cache_data(ttl=TTL_AI_REPORT, show_spinner=False)(func)


def cache_with_custom_ttl(ttl: int):
    """
    自定义TTL的缓存装饰器

    Args:
        ttl: 缓存有效期（秒）

    Returns:
        装饰器函数
    """
    def decorator(func: Callable) -> Callable:
        return st.cache_data(ttl=ttl, show_spinner=False)(func)
    return decorator


def clear_cache(cache_type: str = "all"):
    """
    清除缓存

    Args:
        cache_type: 缓存类型
            - "all": 清除所有缓存
            - "realtime": 清除实时数据缓存
            - "historical": 清除历史数据缓存
            - "ai": 清除AI报告缓存
    """
    if cache_type == "all":
        st.cache_data.clear()
    else:
        # Streamlit目前不支持按类型清除缓存
        # 可以通过重启应用或等待TTL过期
        st.cache_data.clear()


def get_cache_key(*args, **kwargs) -> str:
    """
    生成缓存键

    Args:
        *args: 位置参数
        **kwargs: 关键字参数

    Returns:
        缓存键（MD5哈希）
    """
    key_str = json.dumps({
        'args': args,
        'kwargs': kwargs
    }, sort_keys=True, default=str)
    return hashlib.md5(key_str.encode()).hexdigest()


# 缓存统计（可选，用于监控）
class CacheStats:
    """缓存统计信息"""

    def __init__(self):
        if 'cache_stats' not in st.session_state:
            st.session_state.cache_stats = {
                'hits': 0,
                'misses': 0,
                'last_clear': None
            }

    def record_hit(self):
        """记录缓存命中"""
        st.session_state.cache_stats['hits'] += 1

    def record_miss(self):
        """记录缓存未命中"""
        st.session_state.cache_stats['misses'] += 1

    def get_hit_rate(self) -> float:
        """获取命中率"""
        total = st.session_state.cache_stats['hits'] + st.session_state.cache_stats['misses']
        if total == 0:
            return 0.0
        return st.session_state.cache_stats['hits'] / total

    def reset(self):
        """重置统计"""
        st.session_state.cache_stats = {
            'hits': 0,
            'misses': 0,
            'last_clear': None
        }


# 使用示例：
#
# from src.services.cache_utils import cache_realtime_quote, cache_historical_data
#
# @cache_realtime_quote
# def get_realtime_price(code: str):
#     # 获取实时价格的逻辑
#     return fetch_price(code)
#
# @cache_historical_data
# def get_pb_history(code: str):
#     # 获取历史PB的逻辑
#     return fetch_pb_history(code)
