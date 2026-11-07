# 实施状态（2026-11-07）

## 已合并到 main

| 工作线 | PR | 已落地内容 | CI |
|---|---:|---|---|
| 数据接入 | [#1](https://github.com/just2512/ETF-Backtesting/pull/1) | free-stockdb SDK适配、原始行情读取、复权因子探测、本地覆盖探测脚本、源码静态审计 | PASS |
| 数据审计 | [#2](https://github.com/just2512/ETF-Backtesting/pull/2) | OHLCV基础质量审计、重复日期、异常记录、公司行为/复权因子状态区分 | PASS |
| 指数重叠 | [#3](https://github.com/just2512/ETF-Backtesting/pull/3) | 成分Jaccard、权重重叠、组合穿透暴露计算 | PASS |
| 回测引擎 | [#4](https://github.com/just2512/ETF-Backtesting/pull/4) | 布林带计算、Decimal现金/份额账本、现金变动事件 | PASS |

四个工作线的 GitHub Actions 均通过安装、Lint 和 pytest；main 合并后 CI 也通过。

## 当前代码范围

已建立可运行的 Python 包、共享数据类型、四个模块包和基础单元测试。当前属于第一轮基础设施，不等于完整回测系统。

### 已实现

- free-stockdb 本地 SDK 适配器：请求不复权行情用于成交模拟；独立读取 SDK 暴露的累计复权因子记录。
- 本地探测脚本：对五只候选ETF统计行情数量、首末日期和因子记录数量。
- 数据质量基础检查：空数据、重复日期、OHLC、缺失字段、异常数值。
- 指数重叠计算基础函数：集合重叠、权重重叠、组合穿透暴露。
- 布林带基础计算：20期默认窗口、2倍总体标准差；窗口不足时不生成指标。
- 账本基础：买入、卖出、现金分红入账、显式费用和现金变动。

### 尚未完成

- 用户本机 free-stockdb 服务与真实数据覆盖探测；
- 分红事件数据源及逐笔核验；
- 历史指数成分和历史权重数据源；
- 交易日历与缺失交易日审计；
- 订单模型、下一交易日成交模拟、停牌/涨跌停/最小交易单位；
- 佣金最低收费、其他费用、滑点和价差配置；
- 公共现金池、单只ETF仓位限制和行业暴露约束；
- A/B/C/D四组策略状态机；
- 完整账户估值、收益、回撤和稳健性报告。

## free-stockdb 当前结论

静态源码审计已完成，详见 [FREE_STOCKDB_SOURCE_AUDIT.md](FREE_STOCKDB_SOURCE_AUDIT.md)。

- 日K/分钟K查询：接口能力 PASS。
- 五只ETF实际本地行情覆盖：UNKNOWN。
- 复权因子实际覆盖和语义：UNKNOWN。
- 现金分红事件接口：当前已检查SDK中 MISSING。
- 带生效日期的历史指数成分/权重接口：当前已检查SDK中 MISSING。
- GitHub仓库不包含本地 `data/` 和 LevelDB 文件；`sync_url.txt` 当前无有效源配置。

必须在用户运行 free-stockdb 的本机执行 `python scripts/probe_free_stockdb.py`，才能确认实际数据覆盖。云端GitHub不能读取用户本机的 `127.0.0.1:7899` 或被忽略的本地数据目录。

## 下一阶段

1. 完成交易日历驱动的数据连续性审计。
2. 补充历史成分快照的按日期重建与报告输出。
3. 实现订单/成交引擎，强制信号日与执行日分离。
4. 实现公共资金池和仓位约束。
5. 实现A/B/C/D策略信号模块，统一走同一成交与账本。
6. 以合成fixture跑通端到端后，再接入真实本地数据。
