"""统一的HTTP请求工具，提供重试、超时、降级等功能"""
import time
from typing import Optional, Dict, Any
from datetime import datetime
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class HTTPClient:
    """带重试和超时控制的HTTP客户端"""

    def __init__(
        self,
        timeout: int = 30,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        status_forcelist: tuple = (429, 500, 502, 503, 504)
    ):
        """
        初始化HTTP客户端

        Args:
            timeout: 请求超时时间(秒)
            max_retries: 最大重试次数
            backoff_factor: 重试退避因子
            status_forcelist: 需要重试的HTTP状态码
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()

        # 配置重试策略
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=status_forcelist,
            allowed_methods=["GET", "POST"]
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # 设置默认headers
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def get(
        self,
        url: str,
        params: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        timeout: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        发送GET请求

        Args:
            url: 请求URL
            params: 查询参数
            headers: 额外的请求头
            timeout: 超时时间（不指定则使用默认）

        Returns:
            响应JSON数据，失败返回None
        """
        try:
            req_timeout = timeout or self.timeout
            req_headers = headers or {}

            response = self.session.get(
                url,
                params=params,
                headers=req_headers,
                timeout=req_timeout
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.Timeout:
            print(f"请求超时: {url}")
            return None
        except requests.exceptions.ConnectionError:
            print(f"连接失败: {url}")
            return None
        except requests.exceptions.HTTPError as e:
            print(f"HTTP错误 ({e.response.status_code}): {url}")
            return None
        except Exception as e:
            print(f"请求失败: {url}, 错误: {e}")
            return None

    def post(
        self,
        url: str,
        data: Optional[Dict] = None,
        json: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        timeout: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        发送POST请求

        Args:
            url: 请求URL
            data: 表单数据
            json: JSON数据
            headers: 额外的请求头
            timeout: 超时时间（不指定则使用默认）

        Returns:
            响应JSON数据，失败返回None
        """
        try:
            req_timeout = timeout or self.timeout
            req_headers = headers or {}

            response = self.session.post(
                url,
                data=data,
                json=json,
                headers=req_headers,
                timeout=req_timeout
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.Timeout:
            print(f"请求超时: {url}")
            return None
        except requests.exceptions.ConnectionError:
            print(f"连接失败: {url}")
            return None
        except requests.exceptions.HTTPError as e:
            print(f"HTTP错误 ({e.response.status_code}): {url}")
            return None
        except Exception as e:
            print(f"请求失败: {url}, 错误: {e}")
            return None


# 全局HTTP客户端实例
_default_client: Optional[HTTPClient] = None


def get_http_client() -> HTTPClient:
    """获取全局HTTP客户端实例"""
    global _default_client
    if _default_client is None:
        _default_client = HTTPClient()
    return _default_client


def request_with_retry(
    url: str,
    params: Optional[Dict] = None,
    max_retries: int = 3,
    timeout: int = 30,
    method: str = "GET"
) -> Optional[Dict[str, Any]]:
    """
    带重试的HTTP请求（简化版）

    Args:
        url: 请求URL
        params: 查询参数
        max_retries: 最大重试次数
        timeout: 超时时间
        method: 请求方法

    Returns:
        响应JSON数据，失败返回None
    """
    client = get_http_client()

    for attempt in range(max_retries):
        try:
            if method.upper() == "GET":
                result = client.get(url, params=params, timeout=timeout)
            else:
                result = client.post(url, json=params, timeout=timeout)

            if result is not None:
                return result

            # 如果返回None但还有重试次数，等待后重试
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 指数退避
                print(f"重试 {attempt + 1}/{max_retries}，等待 {wait_time} 秒...")
                time.sleep(wait_time)

        except Exception as e:
            print(f"请求异常 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)

    return None
