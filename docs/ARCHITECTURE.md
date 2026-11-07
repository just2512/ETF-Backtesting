# 系统架构

## 1. 目标与边界

本项目研究多只场内ETF共用公共资金池的长期积累策略。每只ETF保留独立持仓与交易流水，现金由组合层统一调度。数据采集、数据标准化、研究分析和回测执行必须解耦。

## 2. 总体数据流

```text
free-stockdb（候选数据源）
        |
        v
Data Adapter（外部数据适配层）
        |
        v
Normalized Dataset（统一数据契约）
        |
        +----> Data Audit（数据审计）
        |
        +----> Constituent / Industry Exposure（历史成分与暴露）
        |
        v
Strategy Signals（策略信号）
        |
        v
Portfolio Allocator（公共资金池分配）
        |
        v
Execution Engine（下一交易日成交模拟）
        |
        v
Ledger & Accounting（现金、份额、费用、分红账本）
        |
        v
Reports（审计、重叠、回测报告）
```

## 3. 模块职责

- **Adapter**：只负责读取外部数据、字段映射、单位/时区/代码规范化；不在适配器中写策略逻辑。
- **Data Audit**：验证覆盖范围、缺失、重复、异常值、复权和公司行为完整性；产生可机器读取的审计结果。
- **Overlap**：按生效日期重建指数成分与权重，计算ETF之间以及组合穿透后的重叠暴露。
- **Indicators**：纯函数计算布林带等指标，不负责下单。
- **Strategies**：根据截至当日可见的数据生成目标动作，不读取未来数据，不直接修改现金或持仓。
- **Portfolio**：统一约束单只ETF仓位、行业暴露、现金储备和信号优先级。
- **Execution**：按下一交易日真实可成交价格模拟成交，处理停牌、涨跌停、最小交易单位及费用。
- **Accounting**：维护现金、ETF份额、成交、费用、分红和公司行为，保证账本守恒。
- **Reports**：输出审计、暴露、交易明细和绩效统计，并保留配置与数据版本。

## 4. 关键架构约束

1. 策略不得绕过统一 Execution / Accounting。
2. 策略不得直接改写 Portfolio 的现金或持仓状态。
3. 同一回测中，所有策略使用同一数据快照、交易日历、费用规则和成交规则。
4. 所有信号均带有 signal_date、可执行日期和所依据的数据截止时间。
5. 所有结果必须记录配置哈希、数据版本/快照标识、代码版本。
6. 外部数据源格式变化只能影响 Adapter，不应扩散到策略和回测核心。
7. 数据缺失不得静默填充；填充规则必须显式配置并写入报告。

## 5. 建议目录

```text
config/
  etf_universe.yaml
  data_sources.yaml
  backtest.yaml
  trading_costs.yaml
docs/
src/etf_backtesting/
  adapters/
  data/
  overlap/
  indicators/
  strategies/
  portfolio/
  engine/
  reports/
tests/
  fixtures/
data/
  raw/
  normalized/
  snapshots/
reports/
  audit/
  overlap/
  backtests/
scripts/
```

行情原始数据、归一化数据和快照默认留在本地，不提交到Git。测试 fixture 必须小型、可追溯，并明确标记为合成数据或公开样例。

## 6. 与 free-stockdb 的集成原则

通过适配器调用，不直接依赖其内部数据库文件布局。适配器需先验证用户 fork 的真实调用方式、字段定义、复权语义、数据范围和增量同步行为。上游项目文档只能作为线索，不能替代 fork 审计。
