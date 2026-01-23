"""AI-powered stock analysis using Qwen API (Alibaba Cloud)."""
from typing import Optional, Dict, List
from dataclasses import dataclass
from datetime import datetime, date
import requests
import os

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OpenAI = None
    OPENAI_AVAILABLE = False

# Qwen API Configuration (DashScope)
QWEN_MODEL = "qwen3-max"
QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
ENABLE_THINKING = True  # 开启深度思考模式


def get_qwen_api_key() -> Optional[str]:
    """Get Qwen API key from Streamlit secrets or environment variable."""
    # Try Streamlit secrets first (for Streamlit Cloud)
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and 'QWEN_API_KEY' in st.secrets:
            return st.secrets['QWEN_API_KEY']
    except Exception:
        pass

    # Fallback to environment variable
    return os.environ.get('QWEN_API_KEY')


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
    ai_score: int = 3  # AI投资评分 1-5


class AIAnalyzer:
    """AI 股票分析器"""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or get_qwen_api_key()
        self.last_error = None
        self.client = None

        if not OPENAI_AVAILABLE:
            self.last_error = "OpenAI 库未安装或版本过低，请运行: pip install openai>=1.0.0"
        elif self.api_key:
            try:
                self.client = OpenAI(api_key=self.api_key, base_url=QWEN_BASE_URL)
            except Exception as e:
                self.last_error = f"OpenAI 客户端初始化失败: {e}"
        else:
            self.last_error = "未配置 Qwen API Key，请在 Streamlit Secrets 中设置 QWEN_API_KEY"

        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json'
        })

    def _call_openai(self, prompt: str) -> Optional[str]:
        """调用 Qwen API (OpenAI 兼容模式，支持 Thinking 深度思考)"""
        if not self.client:
            self.last_error = "未配置 Qwen API Key，请在 Streamlit Secrets 中设置 QWEN_API_KEY"
            return None

        self.last_error = None

        try:
            # 构建请求参数
            request_params = {
                "model": QWEN_MODEL,
                "messages": [
                    {"role": "system", "content": "你是一位专业的价值投资分析师与买方研究员（Buy-side），擅长用“财务质量 + 估值锚 + 周期位置 + 风险定价”的框架做长期投资决策。你的分析必须：\n- 以事实与数据为依据，明确写出关键假设与推导逻辑，避免空泛结论。\n- 同时覆盖：估值（相对/绝对/历史分位）、基本面（盈利质量/成长/护城河/资本结构）、风险（宏观/行业/公司治理/财务/交易层面）。\n- 给出可执行策略：买入/加仓/减仓/卖出、PB 阈值、仓位建议、触发条件、时间维度（1-3年为主）。\n- 当数据不足时：明确“缺失项”和“对结论的影响”，给出需要补充的数据清单，并在有限数据下给出“保守结论”。\n- 输出语言：中文；格式：严格 Markdown；结构必须与用户要求一致；结论必须克制、可审计，不得夸大确定性。\n- 默认不提供个股“保证收益”表述；可讨论概率、情景、边际安全垫。"},
                    {"role": "user", "content": prompt}
                ]
            }

            # 开启 Thinking 模式时的特殊配置
            if ENABLE_THINKING:
                request_params["extra_body"] = {"enable_thinking": True}
                # Thinking 模式下需要更大的 token 限制
                request_params["max_tokens"] = 16000
            else:
                request_params["temperature"] = 0.7
                request_params["max_tokens"] = 4096

            response = self.client.chat.completions.create(**request_params)

            # 获取回复内容
            message = response.choices[0].message
            content = message.content

            # 如果有 thinking 内容，可以在日志中输出（用于调试）
            if hasattr(message, 'reasoning_content') and message.reasoning_content:
                print(f"[Thinking] 思考过程: {len(message.reasoning_content)} 字符")

            return content

        except Exception as e:
            error_str = str(e)
            if "timeout" in error_str.lower():
                self.last_error = "API请求超时，请稍后重试"
            elif "connect" in error_str.lower() or "network" in error_str.lower():
                self.last_error = "网络连接失败，请检查网络"
            elif "429" in error_str or "rate" in error_str.lower():
                self.last_error = "API请求过于频繁，请稍后重试"
            elif "401" in error_str or "InvalidApiKey" in error_str:
                self.last_error = "API密钥无效，请检查配置"
            elif "insufficient" in error_str.lower() or "quota" in error_str.lower():
                self.last_error = "API配额已用尽，请检查账户余额"
            else:
                self.last_error = f"API调用异常: {error_str[:100]}"
            print(f"Qwen API call failed: {e}")

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
        prompt = f"""你是一位专业的价值投资分析师。请根据以下数据，为这只股票生成一份“机构级”投资分析报告。

【股票数据摘要】
{data_summary}

【分析要求与方法论】
1) 请以价值投资框架输出：商业模式/护城河 → 财务质量 → 增长可持续性 → 估值锚（PB/ROE/分红/周期）→ 风险定价 → 操作建议。
2) 估值分析必须包含：
   - 当前 PB/PE（若有）、对应历史分位（例如 10%/50%/90%）、与同业可比（若有）；
   - 用 PB-ROE 逻辑解释“PB 是否合理”（例如：ROE 可持续性、杠杆驱动、周期高点/低点）；
   - 给出至少 3 种情景：保守/基准/乐观（分别说明 ROE、增长、利润率的假设），并说明估值可能的回归路径（均值回归/再评级/杀估值）。
3) 基本面分析必须覆盖并量化（尽可能用数据/区间表达）：
   - 盈利能力：ROE 拆解（净利率×周转×杠杆）、毛利率/净利率稳定性、费用率变化；
   - 成长性：营收/利润 CAGR 或近几年增速的趋势与波动原因；
   - 财务健康：资产负债率、短债压力、利息覆盖、现金及等价物安全垫；
   - 现金流质量：经营现金流/净利润匹配度、资本开支强度、自由现金流（若有）；
   - 股东回报：分红率、股息率、回购（若有）、融资摊薄风险；
   - 公司治理/一次性损益/会计质量（若数据缺失需提示）。
4) 风险提示必须分层：
   - 宏观与利率环境、行业周期与竞争格局、公司经营/产品/客户集中度、财务风险（应收/存货/商誉/杠杆）、政策与合规、黑天鹅与流动性风险。
   - 每条风险给出“触发信号/观察指标”（例如：毛利率下滑>2pct、应收周转显著变差等）。
5) 投资建议必须“可执行”：
   - 明确建议：买入/持有/卖出（只能选其一作为主建议），并给出理由；
   - 给出仓位建议（例如：轻仓/中仓/重仓，或 10%/30%/50% 的区间建议）；
   - 给出“买入条件/加仓条件/减仓条件/止损或止盈条件”（用 PB 或关键经营指标触发）。
6) PB阈值建议必须结合历史 PB 分布与公司质地：
   - 给出：建议买入PB、加仓PB、卖出PB（必须为具体数值或区间）；
   - 给出阈值背后的依据（历史分位、ROE 中枢、周期位置、风险溢价）。
7) 输出必须严格遵循下列 Markdown 结构，不得增删标题；每个章节尽量用条目化呈现，并在关键结论后写出“依据（数据点/假设）”。

【输出格式（严格遵循，使用Markdown）】
## 一句话总结
(用一句话概括这只股票的投资价值，包含“估值位置 + 基本面质量 + 风险一句话”)

## 估值分析
- 当前估值水平：(...)
- 历史对比与分位：(...)
- 同业对比（若无数据写“数据缺失”并说明影响）：(...)
- PB-ROE合理性判断：(...)
- 情景分析（保守/基准/乐观）：每个情景包含“关键假设 + 估值推演 + 触发因素”
- 结论：当前偏低估/合理/偏高估（必须三选一），并说明置信度（高/中/低）

## 基本面分析
- 商业模式与护城河：(...)
- 盈利能力：(...)
- 成长性：(...)
- 财务健康：(...)
- 现金流与资本开支：(...)
- 股东回报与资本配置：(...)
- 经营质量综合判断：给出强/中/弱，并解释

## 风险提示
- 宏观/利率风险：...（触发信号：...）
- 行业竞争与周期风险：...（触发信号：...）
- 公司经营与客户/产品风险：...（触发信号：...）
- 财务与报表质量风险：...（触发信号：...）
- 政策/合规/其他风险：...（触发信号：...）

## 投资建议
- 结论：买入/持有/卖出（只能选一个）
- 理由（条目化，至少3条，分别对应估值/基本面/风险）
- 操作计划（必须包含）：初始仓位、加仓规则、减仓规则、止损/止盈条件、观察指标清单
- 适合投资者类型：稳健/平衡/进取（说明原因）

## PB阈值建议
- 建议买入PB：...
- 建议加仓PB：...
- 建议卖出PB：...
- 依据：历史分位/ROE中枢/周期位置/风险溢价（逐条说明）

## AI投资评分
评分: X分
(用3-6条要点解释为什么是这个分数；若数据缺失导致不确定性，必须下调或标注)"""

        # 调用 Qwen3-max API
        response = self._call_openai(prompt)

        if not response:
            return None

        # 解析响应
        report = self._parse_report(response, fundamental)

        return report

    def _parse_report(self, response: str, fundamental: FundamentalData) -> AnalysisReport:
        """解析 AI 响应为结构化报告"""
        import re

        # 简单解析各部分
        sections = {
            'summary': '',
            'valuation': '',
            'fundamental': '',
            'risk': '',
            'suggestion': '',
            'pb_recommendation': '',
            'ai_score': ''
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
            elif '投资建议' in line and 'AI' not in line:
                if current_section:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = 'suggestion'
                current_content = []
            elif 'PB阈值' in line or 'pb阈值' in line.lower():
                if current_section:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = 'pb_recommendation'
                current_content = []
            elif 'AI投资评分' in line or 'AI评分' in line or 'ai评分' in line_lower:
                if current_section:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = 'ai_score'
                current_content = []
            elif current_section:
                if not line.startswith('#'):
                    current_content.append(line)

        if current_section:
            sections[current_section] = '\n'.join(current_content).strip()

        # 提取AI评分数字
        ai_score = 3  # 默认3分
        score_text = sections.get('ai_score', '')
        if score_text:
            # 尝试匹配 "评分: X分" 或 "X分" 或数字
            match = re.search(r'(\d)[分/]', score_text)
            if match:
                ai_score = int(match.group(1))
            else:
                match = re.search(r'[：:]\s*(\d)', score_text)
                if match:
                    ai_score = int(match.group(1))
        # 确保在1-5范围内
        ai_score = max(1, min(5, ai_score))

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
            full_report=response,
            ai_score=ai_score
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
