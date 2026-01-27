# 部署日志

## 部署时间
2026-01-27

## 部署环境
- Python: 3.11.14 (Conda: UBA_CC)
- 操作系统: Windows
- 代码仓库: https://github.com/yizhidianlu/UBA

## 部署步骤

### 1. 安装依赖 ✓
```bash
conda activate UBA_CC
pip install -r requirements.txt
```

**新增依赖**:
- tushare>=1.2.89
- python-dotenv>=1.0.0
- tenacity>=8.2.0
- akshare>=1.12.0 (更新)

### 2. 配置环境变量 ✓
在 `.streamlit/secrets.toml` 中配置：
```toml
TUSHARE_TOKEN = "b49f13cb0fda07acdb4766d9bb8d8e63bc887607428fbe6acac2dcc9"
QWEN_API_KEY = "sk-01847ff81a1b4ee894a8dc1afd773797"
```

### 3. 数据库迁移 ✓
```bash
python scripts/migrate_add_pb_fields.py
python scripts/migrate_add_unique_constraint.py
```

**迁移内容**:
- 添加 `pb_method` 字段（PB计算方法）
- 添加 `report_period` 字段（财报期）
- 添加 `UNIQUE(asset_id, date)` 约束
- 添加 `ix_valuation_asset_date` 索引
- 清理重复数据（0条）

### 4. 功能测试 ✓

| 测试项 | 结果 | 说明 |
|--------|------|------|
| Tushare Token | ✓ | 成功从 secrets.toml 读取 |
| HTTP客户端 | ✓ | 带重试和超时的HTTP工具初始化成功 |
| StockAnalyzer | ✓ | Tushare API 可用 |
| 数据库约束 | ✓ | 唯一约束已生效 |
| 新增字段 | ✓ | pb_method, report_period 字段存在 |
| 股票信息 | ✓ | 成功获取贵州茅台(600519.SH)信息 |

### 5. Git提交 ✓
```bash
git add ...
git commit -m "feat: 根据代码评审完成P0优先级改进"
git push origin main
```

**提交哈希**: 4403abe

## 已完成的改进 (P0)

### 1. 安全性修复
- ✓ 移除硬编码 Tushare Token
- ✓ 使用环境变量/Streamlit secrets 配置
- ✓ 添加降级逻辑（无 Token 时使用东方财富备用）

### 2. 数据库完整性
- ✓ 为 Valuation 表添加 UniqueConstraint
- ✓ 添加索引提升查询性能
- ✓ 防止重复数据写入

### 3. 数据正确性
- ✓ 修复 valuation.py price 字段错误
- ✓ 统一 PB 数据源和字段
- ✓ 记录数据来源和计算方法

### 4. 稳定性增强
- ✓ 创建统一的 HTTP 工具层
- ✓ 自动重试 + 指数退避 + 超时控制
- ✓ 优化后台扫描器，防止多实例启动

### 5. 依赖完整性
- ✓ 更新 requirements.txt
- ✓ 所有依赖安装成功

### 6. 文档完善
- ✓ 创建 IMPROVEMENTS.md
- ✓ 创建 .env.example
- ✓ 创建 .streamlit/secrets.toml.example

## 新增文件

1. `src/services/http_utils.py` - 统一HTTP工具（334行）
2. `scripts/migrate_add_pb_fields.py` - 字段迁移脚本
3. `scripts/migrate_add_unique_constraint.py` - 约束迁移脚本
4. `IMPROVEMENTS.md` - 改进说明文档
5. `.env.example` - 环境变量配置示例
6. `.streamlit/secrets.toml.example` - Secrets配置示例

## 下一步建议 (P1)

参考 `IMPROVEMENTS.md` 和 `UBA_code_review.md` 第2周计划：

1. **投资逻辑增强**:
   - 加入 ROE 质量过滤
   - 信号冷却期/去抖
   - 行业分组阈值模板

2. **仓位系统增强**:
   - 引入资金账 (NAV/Cash)
   - 交易成本模型

3. **性能优化**:
   - Streamlit 缓存优化
   - AI 报告数据快照

4. **监控与日志**:
   - 错误日志落库
   - 数据质量监控

## 启动应用

```bash
conda activate UBA_CC
streamlit run app.py
```

访问: http://localhost:8501

## 部署人员
Claude Code (Claude Opus 4.5)

## 备注
- secrets.toml 已添加到 .gitignore，不会被提交
- 数据库文件 (uba.db) 已更新，建议备份
- 所有改进遵循代码评审文档建议
