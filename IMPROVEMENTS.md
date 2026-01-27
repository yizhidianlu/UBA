# 代码改进记录

根据代码评审意见，已完成以下 P0（必须立即修）优先级的改进：

## 已完成的改进 (P0)

### 1. ✅ 修复 Tushare Token 硬编码问题
**问题**: `stock_analyzer.py` 中硬编码 Token，存在安全风险

**修复**:
- 移除硬编码 Token
- 使用 `get_tushare_token()` 函数从环境变量/Streamlit secrets 获取
- 添加降级逻辑：无 Token 时使用东方财富备用方案

**配置方法**:
```bash
# 方法1: 环境变量
export TUSHARE_TOKEN="your_token_here"

# 方法2: Streamlit secrets (.streamlit/secrets.toml)
[secrets]
TUSHARE_TOKEN = "your_token_here"
```

---

### 2. ✅ 数据库添加唯一性约束和索引
**问题**: `Valuation` 表的 `Meta.unique_together` 对 SQLAlchemy 不生效，会产生重复数据

**修复**:
- 移除无效的 `Meta` 类
- 添加 `UniqueConstraint("asset_id", "date")` 防止重复数据
- 添加 `Index("ix_valuation_asset_date", "asset_id", "date")` 加速查询

**影响**: 现有数据不会自动去重，建议手动清理重复数据

---

### 3. ✅ 修复 valuation.py price 字段错误
**问题**: 第62行将市值(`total_mv`)写入 `price` 字段，应该是收盘价

**修复**:
- 从 `close` 字段获取真实收盘价
- 如果 `close` 不存在，`price` 设为 None

**影响**: 新获取的数据会有正确的价格，旧数据建议重新抓取

---

### 4. ✅ 更新 requirements.txt 添加缺失依赖
**新增依赖**:
```txt
tushare>=1.2.89          # Tushare API
python-dotenv>=1.0.0     # 环境变量加载
tenacity>=8.2.0          # 重试机制
```

**安装方法**:
```bash
pip install -r requirements.txt
```

---

### 5. ✅ 统一 PB 数据源和字段
**问题**: PB 数据来源不一致，难以审计和追溯

**修复**:
- `Valuation` 表新增字段:
  - `pb_method`: PB计算方法 (direct/calculated)
  - `report_period`: 财报期 (可选)
- 所有数据源都记录来源和计算方法:
  - Tushare: `data_source='tushare', pb_method='direct'`
  - 东方财富: `data_source='eastmoney', pb_method='calculated'`
  - AkShare: `data_source='akshare', pb_method='direct'`

**数据库迁移**:
```bash
python scripts/migrate_add_pb_fields.py
```

---

### 6. ✅ 优化后台扫描器与 Streamlit 集成
**问题**: 后台线程在 Streamlit rerun 时可能重复启动

**修复**:
- 启动前检查数据库中的运行状态，防止多实例启动
- `stop_scan()` 方法会自动清理数据库状态
- 新增 `reset_scan_status()` 方法用于手动重置异常状态

**使用建议**:
- 如果扫描器状态异常，可调用 `scanner.reset_scan_status()` 重置

---

### 7. ✅ 网络请求添加重试和降级机制
**新增**: `src/services/http_utils.py` - 统一的HTTP工具层

**功能**:
- 自动重试 (默认3次)
- 指数退避 (0.5, 1, 2秒)
- 超时控制 (默认30秒)
- 对 429, 500, 502, 503, 504 状态码自动重试
- 统一错误处理和日志

**使用方法**:
```python
from src.services.http_utils import HTTPClient

client = HTTPClient(timeout=30, max_retries=3)
data = client.get(url, params=params)
```

**已更新的模块**:
- `stock_analyzer.py`
- `background_scanner.py`

---

## 使用说明

### 首次运行
```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 Tushare Token (二选一)
export TUSHARE_TOKEN="your_token_here"
# 或在 .streamlit/secrets.toml 中配置

# 3. 运行数据库迁移
python scripts/migrate_add_pb_fields.py

# 4. 启动应用
streamlit run app.py
```

### 数据完整性检查

运行以下 SQL 检查是否有重复数据：
```sql
SELECT asset_id, date, COUNT(*) as cnt
FROM valuations
GROUP BY asset_id, date
HAVING cnt > 1;
```

如有重复，可以手动清理：
```sql
DELETE FROM valuations
WHERE id NOT IN (
    SELECT MIN(id)
    FROM valuations
    GROUP BY asset_id, date
);
```

---

## 下一步建议 (P1 - 强烈建议)

以下改进建议参考评审文档第2周计划：

1. **投资逻辑增强**:
   - 加入 ROE 质量过滤
   - 信号冷却期/去抖
   - 行业分组阈值模板

2. **仓位系统增强**:
   - 引入资金账 (NAV/Cash)
   - 交易成本模型 (手续费、滑点)

3. **Streamlit 缓存优化**:
   - 实时行情缓存 (ttl=10秒)
   - 历史数据缓存 (ttl=3600秒)

4. **AI 报告优化**:
   - 保存输入数据快照
   - 记录模型和成本估算

---

## 自测清单

- [ ] PB一致性: 同一股票的历史PB和实时PB差异 <10%
- [ ] 重复写入: 连续点击"刷新PB"10次，数据库只有一天一条
- [ ] 港股支持: 港股能获取PB并触发信号
- [ ] 并发安全: 两个浏览器同时打开不会产生重复线程
- [ ] 脱网降级: 断网/超时时UI优雅降级而不白屏

---

## 问题反馈

如遇到问题，请检查：
1. 是否运行了数据库迁移脚本
2. 是否安装了所有新依赖
3. Tushare Token 是否正确配置
4. 日志中是否有错误信息

修改时间: 2026-01-27
