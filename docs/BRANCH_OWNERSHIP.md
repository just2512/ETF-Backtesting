# 工作线目录所有权与接口冻结

## 四条工作线

所有功能分支均从 `main` 的设计基线提交创建；不得自行改变本文档定义的跨模块契约。

| 分支 | 独占目录 | 允许新增 | 不得直接修改 |
|---|---|---|---|
| `work/data-adapter` | `src/etf_backtesting/adapters/` | 数据源探测、free-stockdb适配、外部字段映射 | `data/contract.py`、账本、策略 |
| `work/data-audit` | `src/etf_backtesting/data/`、`scripts/audit_data.py`、`tests/data/` | 数据质量规则、审计报告生成、审计测试 | Adapter外部API语义、回测账本 |
| `work/index-overlap` | `src/etf_backtesting/overlap/`、`tests/overlap/` | 历史成分、权重、行业暴露分析 | 数据契约、成交引擎 |
| `work/backtest-engine` | `src/etf_backtesting/indicators/`、`strategies/`、`portfolio/`、`engine/`、`reports/`、`tests/engine/` | 指标、策略、组合分配、成交与会计 | Adapter内部实现、数据源配置 |

共享契约和项目级配置由 `main` 集成维护。各分支需要调整共享契约时，先提出独立、最小化的契约提交，确认兼容后再继续实现；禁止在四个分支分别复制或分叉契约。

## 冻结接口

### 1. 标准行情记录

主键为 `(symbol, trade_date)`。字段语义遵循 `DATA_CONTRACT.md`。原始市场价、复权价和复权因子必须分开存储；成交模拟只消费原始市场价。

### 2. Adapter 边界

Adapter 负责外部读取和规范化，向上提供标准化数据集及来源元数据。它不负责填补缺失数据、不负责策略信号、不负责成交。

### 3. Audit 边界

Audit 接收标准化数据和来源元数据，输出机器可读的状态、问题明细、覆盖区间及审计摘要。不能静默修复或删除异常记录。

### 4. Overlap 边界

Overlap 只消费按生效日期有效的历史成分与权重数据；缺少权重时必须降级报告，不得用当前成分回填历史。

### 5. Strategy / Portfolio / Execution / Accounting 边界

Strategy 只生成带日期的目标动作或订单意图；Portfolio 负责资金与风险约束；Execution 负责成交模拟；Accounting 负责现金、份额、费用和分红账本。策略不得直接修改现金或持仓。

## 文件所有权补充规则

- 每个工作线只提交其独占目录和对应测试。
- 修改共享接口必须在提交说明中列出兼容性影响。
- 不允许两个工作线并发写同一文件。
- 跨目录改动拆成接口提交与实现提交，不在一个大提交里混合。
- 每条工作线合并前同步最新 `main`，运行本模块测试；合并后由 `main` 运行完整集成测试。
- 数据、缓存、快照和大型报告不提交Git。

## 工作线验收

- Adapter：能连接/探测配置的数据服务，明确返回可用字段、数据范围和来源；不可访问本机服务时输出 `UNKNOWN`，不伪造数据。
- Audit：使用小型fixture验证缺失、重复、OHLC、复权与分红审计规则。
- Overlap：使用带生效日期和历史权重的fixture验证成分变更、权重重叠与组合穿透。
- Engine：验证信号/成交时序、订单可成交性、费用和账本守恒。
