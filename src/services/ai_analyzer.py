"""AI-powered stock analysis using OpenAI API."""
from typing import Optional, Dict, List
from dataclasses import dataclass
from datetime import datetime, date
import requests
import os

from openai import OpenAI

# OpenAI API Configuration
OPENAI_MODEL = "gpt-4.1"


def get_openai_api_key() -> Optional[str]:
    """Get OpenAI API key from Streamlit secrets or environment variable."""
    # Try Streamlit secrets first (for Streamlit Cloud)
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and 'OPENAI_API_KEY' in st.secrets:
            return st.secrets['OPENAI_API_KEY']
    except Exception:
        pass

    # Fallback to environment variable
    return os.environ.get('OPENAI_API_KEY')


@dataclass
class FundamentalData:
    """基本面数据"""
    code: str
    name: str
    industry: str
    market_cap: Optional[float]  # 市值(亿)
    pe_ttm: Optional[float]  # 市盈率TTM
    pb: Optional[float]  # 市净率
    roe: Optional[float]  # ROE
    revenue_yoy: Optional[float]  # 营收同比增长
    profit_yoy: Optional[float]  # 净利润同比增长
    gross_margin: Optional[float]  # 毛利率
    debt_ratio: Optional[float]  # 资产负债率
    current_price: Optional[float]
    week_52_high: Optional[float]
    week_52_low: Optional[float]


@dataclass
class AnalysisReport:
    """分析报告"""
    code: str
    name: str
    generated_at: datetime
    summary: str  # 一句话总结
    valuation_analysis: str  # 估值分析
    fundamental_analysis: str  # 基本面分析
    risk_analysis: str  # 风险分析
    investment_suggestion: str  # 投资建议
    pb_recommendation: str  # PB阈值建议
    full_report: str  # 完整报告


class AIAnalyzer:
    """AI 股票分析器"""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or get_openai_api_key()
        self.last_error = None
        self.client = None
        if self.api_key:
            self.client = OpenAI(api_key=self.api_key)
        else:
            self.last_error = "未配置 OpenAI API Key，请在 Streamlit Secrets 中设置 OPENAI_API_KEY"
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json'
        })

    def _call_openai(self, prompt: str) -> Optional[str]:
        """调用 OpenAI API"""
        if not self.client:
            self.last_error = "未配置 OpenAI API Key，请在 Streamlit Secrets 中设置 OPENAI_API_KEY"
            return None

        self.last_error = None

        try:
            response = self.client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "你是一位专业的价值投资分析师，擅长分析股票基本面和估值。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=4096
            )
            return response.choices[0].message.content

        except Exception as e:
            error_str = str(e)
            if "timeout" in error_str.lower():
                self.last_error = "API请求超时，请稍后重试"
            elif "connect" in error_str.lower() or "network" in error_str.lower():
                self.last_error = "网络连接失败，请检查网络"
            elif "429" in error_str or "rate" in error_str.lower():
                self.last_error = "API请求过于频繁，请稍后重试"
            elif "401" in error_str or "invalid" in error_str.lower() and "key" in error_str.lower():
                self.last_error = "API密钥无效，请检查配置"
            elif "insufficient_quota" in error_str.lower():
                self.last_error = "API配额已用尽，请检查账户余额"
            else:
                self.last_error = f"API调用异常: {error_str[:100]}"
            print(f"OpenAI API call failed: {e}")

        return None

    def fetch_fundamental_data(self, code: str) -> Optional[FundamentalData]:
        """获取股票基本面数据"""
        # 解析代码
        code = code.upper()
        if '.SH' in code:
            pure_code = code.replace('.SH', '')
            secid = f"1.{pure_code}"
        elif '.SZ' in code:
            pure_code = code.replace('.SZ', '')
            secid = f"0.{pure_code}"
        else:
            pure_code = code
            if code.startswith('6'):
                secid = f"1.{code}"
            else:
                secid = f"0.{code}"

        try:
            # 获取实时行情和基本指标
            url = 'https://push2.eastmoney.com/api/qt/stock/get'
            params = {
                'secid': secid,
                'fields': 'f43,f44,f45,f46,f47,f48,f50,f51,f52,f57,f58,f84,f85,f92,f116,f117,f127,f162,f167,f168,f169,f170',
                'ut': 'fa5fd1943c7b386f172d6893dbfba10b'
            }
            resp = self.session.get(url, params=params, timeout=10)
            data = resp.json()

            if not data.get('data'):
                return None

            d = data['data']
            price = d.get('f43', 0) / 100 if d.get('f43') else None
            bvps = d.get('f92')
            pb = round(price / bvps, 2) if price and bvps and bvps > 0 else None

            # 获取更多财务数据
            finance_data = self._fetch_finance_data(pure_code, secid)

            return FundamentalData(
                code=code if '.' in code else (f"{code}.SH" if code.startswith('6') else f"{code}.SZ"),
                name=d.get('f58', ''),
                industry=d.get('f127', ''),
                market_cap=d.get('f116') / 100000000 if d.get('f116') else None,  # 转为亿
                pe_ttm=d.get('f162') / 100 if d.get('f162') else None,
                pb=pb,
                roe=finance_data.get('roe'),
                revenue_yoy=finance_data.get('revenue_yoy'),
                profit_yoy=finance_data.get('profit_yoy'),
                gross_margin=finance_data.get('gross_margin'),
                debt_ratio=finance_data.get('debt_ratio'),
                current_price=price,
                week_52_high=d.get('f44', 0) / 100 if d.get('f44') else None,
                week_52_low=d.get('f45', 0) / 100 if d.get('f45') else None
            )

        except Exception as e:
            print(f"获取基本面数据失败: {e}")
            return None

    def _fetch_finance_data(self, pure_code: str, secid: str) -> Dict:
        """获取财务数据"""
        finance = {}

        try:
            # 尝试获取财务指标
            url = "https://datacenter.eastmoney.com/securities/api/data/get"
            params = {
                'type': 'RPT_F10_FINANCE_MAINFINADATA',
                'sty': 'ALL',
                'filter': f'(SECUCODE="{pure_code}.SZ")' if pure_code.startswith(('0', '3')) else f'(SECUCODE="{pure_code}.SH")',
                'p': '1',
                'ps': '1',
                'sr': '-1',
                'st': 'REPORT_DATE',
                'source': 'HSF10',
                'client': 'PC'
            }

            resp = self.session.get(url, params=params, timeout=10)
            data = resp.json()

            if (data.get('result') or {}).get('data'):
                item = data['result']['data'][0]
                finance['roe'] = item.get('ROEJQ')  # ROE
                finance['gross_margin'] = item.get('XSMLL')  # 毛利率
                finance['debt_ratio'] = item.get('ZCFZL')  # 资产负债率

            # 获取增长数据
            growth_url = "https://datacenter.eastmoney.com/securities/api/data/get"
            growth_params = {
                'type': 'RPT_F10_FINANCE_GINCREDATA',
                'sty': 'ALL',
                'filter': f'(SECUCODE="{pure_code}.SZ")' if pure_code.startswith(('0', '3')) else f'(SECUCODE="{pure_code}.SH")',
                'p': '1',
                'ps': '1',
                'sr': '-1',
                'st': 'REPORT_DATE',
                'source': 'HSF10',
                'client': 'PC'
            }

            resp = self.session.get(growth_url, params=growth_params, timeout=10)
            growth_data = resp.json()

            if (growth_data.get('result') or {}).get('data'):
                item = growth_data['result']['data'][0]
                finance['revenue_yoy'] = item.get('YYZSRTBZZ')  # 营收同比
                finance['profit_yoy'] = item.get('GSJLRTBZZ')  # 净利润同比

        except Exception as e:
            print(f"获取财务数据失败: {e}")

        return finance

    def generate_analysis_report(
        self,
        fundamental: FundamentalData,
        pb_history: List[Dict] = None,
        threshold_buy: float = None,
        threshold_add: float = None,
        threshold_sell: float = None
    ) -> Optional[AnalysisReport]:
        """生成 AI 分析报告"""

        # 构建分析数据摘要
        pe_str = f"{fundamental.pe_ttm:.2f}倍" if fundamental.pe_ttm else "未知"
        pb_str = f"{fundamental.pb:.2f}倍" if fundamental.pb else "未知"
        cap_str = f"{fundamental.market_cap:.0f}亿元" if fundamental.market_cap else "未知"
        roe_str = f"{fundamental.roe:.2f}%" if fundamental.roe else "未知"
        gm_str = f"{fundamental.gross_margin:.2f}%" if fundamental.gross_margin else "未知"
        dr_str = f"{fundamental.debt_ratio:.2f}%" if fundamental.debt_ratio else "未知"
        rev_str = f"{fundamental.revenue_yoy:.2f}%" if fundamental.revenue_yoy else "未知"
        profit_str = f"{fundamental.profit_yoy:.2f}%" if fundamental.profit_yoy else "未知"
        price_str = f"{fundamental.current_price:.2f}元" if fundamental.current_price else "未知"

        data_summary = f"""
股票信息:
- 名称: {fundamental.name}
- 代码: {fundamental.code}
- 行业: {fundamental.industry}
- 当前价格: {price_str}

估值指标:
- 市盈率(PE-TTM): {pe_str}
- 市净率(PB): {pb_str}
- 总市值: {cap_str}

财务指标:
- ROE(净资产收益率): {roe_str}
- 毛利率: {gm_str}
- 资产负债率: {dr_str}
- 营收同比增长: {rev_str}
- 净利润同比增长: {profit_str}
"""

        # 添加PB历史数据
        if pb_history:
            pb_values = [h['pb'] for h in pb_history if h.get('pb')]
            if pb_values:
                min_pb = min(pb_values)
                max_pb = max(pb_values)
                avg_pb = sum(pb_values) / len(pb_values)
                current_pb = fundamental.pb if fundamental.pb else avg_pb
                percentile = len([p for p in pb_values if p <= current_pb]) / len(pb_values) * 100
                data_summary += f"""
PB历史数据 (近5年):
- 最低PB: {min_pb:.2f}
- 最高PB: {max_pb:.2f}
- 平均PB: {avg_pb:.2f}
- 当前PB分位: {percentile:.1f}%
"""

        if threshold_buy:
            add_str = f"PB <= {threshold_add:.2f}" if threshold_add else "未设置"
            sell_str = f"PB >= {threshold_sell:.2f}" if threshold_sell else "未设置"
            data_summary += f"""
用户设定阈值:
- 请客价(买入): PB <= {threshold_buy:.2f}
- 加仓价: {add_str}
- 退出价(卖出): {sell_str}
"""

        # 构建 Prompt
        prompt = f"""你是一位专业的价值投资分析师。请根据以下数据，为这只股票生成一份专业的投资分析报告。

{data_summary}

请按以下格式输出分析报告(使用Markdown格式):

## 一句话总结
(用一句话概括这只股票的投资价值)

## 估值分析
(分析当前估值水平，与历史估值对比，判断是否被低估或高估)

## 基本面分析
(分析公司的盈利能力、成长性、财务健康状况)

## 风险提示
(指出投资这只股票的主要风险)

## 投资建议
(给出明确的投资建议：买入/持有/卖出，以及理由)

## PB阈值建议
(根据历史PB数据和公司质地，建议合理的买入PB、加仓PB和卖出PB)

请确保分析客观、专业，不要过于乐观或悲观。"""

        # 调用 Gemini
        response = self._call_openai(prompt)

        if not response:
            return None

        # 解析响应
        report = self._parse_report(response, fundamental)

        return report

    def _parse_report(self, response: str, fundamental: FundamentalData) -> AnalysisReport:
        """解析 AI 响应为结构化报告"""

        # 简单解析各部分
        sections = {
            'summary': '',
            'valuation': '',
            'fundamental': '',
            'risk': '',
            'suggestion': '',
            'pb_recommendation': ''
        }

        current_section = None
        current_content = []

        for line in response.split('\n'):
            line_lower = line.lower()

            if '一句话总结' in line or 'summary' in line_lower:
                if current_section:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = 'summary'
                current_content = []
            elif '估值分析' in line or 'valuation' in line_lower:
                if current_section:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = 'valuation'
                current_content = []
            elif '基本面分析' in line or 'fundamental' in line_lower:
                if current_section:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = 'fundamental'
                current_content = []
            elif '风险' in line:
                if current_section:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = 'risk'
                current_content = []
            elif '投资建议' in line:
                if current_section:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = 'suggestion'
                current_content = []
            elif 'PB阈值' in line or 'pb阈值' in line.lower():
                if current_section:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = 'pb_recommendation'
                current_content = []
            elif current_section:
                if not line.startswith('#'):
                    current_content.append(line)

        if current_section:
            sections[current_section] = '\n'.join(current_content).strip()

        return AnalysisReport(
            code=fundamental.code,
            name=fundamental.name,
            generated_at=datetime.now(),
            summary=sections['summary'] or "暂无总结",
            valuation_analysis=sections['valuation'] or "暂无估值分析",
            fundamental_analysis=sections['fundamental'] or "暂无基本面分析",
            risk_analysis=sections['risk'] or "暂无风险分析",
            investment_suggestion=sections['suggestion'] or "暂无投资建议",
            pb_recommendation=sections['pb_recommendation'] or "暂无PB建议",
            full_report=response
        )

    def quick_analysis(self, code: str) -> Optional[str]:
        """快速分析（简化版）"""
        fundamental = self.fetch_fundamental_data(code)

        if not fundamental:
            return None

        price_str = f"{fundamental.current_price:.2f}元" if fundamental.current_price else "未知"
        pe_str = f"{fundamental.pe_ttm:.2f}倍" if fundamental.pe_ttm else "未知"
        pb_str = f"{fundamental.pb:.2f}倍" if fundamental.pb else "未知"
        cap_str = f"{fundamental.market_cap:.0f}亿" if fundamental.market_cap else "未知"

        prompt = f"""请用3-5句话简要分析 {fundamental.name}({fundamental.code}) 的投资价值:

当前数据:
- 股价: {price_str}
- PE: {pe_str}
- PB: {pb_str}
- 市值: {cap_str}
- 行业: {fundamental.industry}

请简要评估其估值水平和投资价值。"""

        return self._call_openai(prompt)
