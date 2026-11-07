# 实施状态（2026-11-07）

## 已合并到 main

| 工作线 | PR | 已落地内容 | CI |
|---|---:|---|---|
| 数据接入 | [#1](https://github.com/just2512/ETF-Backtesting/pull/1)、[#8](https://github.com/just2512/ETF-Backtesting/pull/8)、[#10](https://github.com/just2512/ETF-Backtesting/pull/10)、[#12](https://github.com/just2512/ETF-Backtesting/pull/12)、[#14](https://github.com/just2512/ETF-Backtesting/pull/14)、[#17](https://github.com/just2512/ETF-Backtesting/pull/17) | free-stockdb适配、原始行情探测、质量汇总、复权因子语义门禁、JSON本地报告 | PASS |
| 数据审计 | [#2](https://github.com/just2512/ETF-Backtesting/pull/2)、[#5](https://github.com/just2512/ETF-Backtesting/pull/5)、[#13](https://github.com/just2512/ETF-Backtesting/pull/13) | OHLCV、重复/异常、交易日历缺口、硬门禁状态汇总 | PASS |
| 指数重叠 | [#3](https://github.com/just2512/ETF-Backtesting/pull/3)、[#6](https://github.com/just2512/ETF-Backtesting/pull/6)、[#15](https://github.com/just2512/ETF-Backtesting/pull/15) | 历史生效区间快照、成分/权重重叠、组合穿透、CSV报告 | PASS |
| 回测引擎 | [#4](https://github.com/just2512/ETF-Backtesting/pull/4)、[#7](https://github.com/just2512/ETF-Backtesting/pull/7)、[#9](https://github.com/just2512/ETF-Backtesting/pull/9)、[#11](https://github.com/just2512/ETF-Backtesting/pull/11)、[#18](https://github.com/just2512/ETF-Backtesting/pull/18) | 布林/定投信号、S0/S1/S2卖出、订单编译、下一交易日成交、公共资金池与行业门禁、分红账本、单位净值和组合运行器 | PASS |

四个工作线均已合并，main 最新集成 CI：62 passed，Lint PASS。

## 当前代码范围

已建立可运行的 Python 包、共享数据类型、四个模块包和基础单元测试。当前属于第一轮基础设施，不等于完整回测系统。

### 已实现

- free-stockdb 本地 SDK 适配器：请求不复权行情用于成交模拟；独立读取SDK累计复权因子；复权指标序列只有在语义独立核验后才允许读取。
- 本地探测脚本：对五只候选ETF统计行情数量、首末日期、因子记录数量，按时间升序规范化，并输出OHLC质量和硬门禁汇总；支持本地JSON文件输出。
- 数据质量检查：空数据、重复日期、OHLC、缺失字段、异常数值；提供权威交易日历时可识别缺失交易日，无日历时标记UNKNOWN。
- 指数重叠：集合重叠、权重重叠、组合穿透暴露；可按成分生效区间重建历史快照，并拒绝权重缺失或不归一。
- 布林带：20期默认窗口、2倍总体标准差；窗口不足时不生成指标。
- 账本：买入、卖出、现金分红和外部投入独立记账；按平均成本法维护剩余成本和已实现盈亏。
- 成交模拟与组合运行器：收盘信号日期与下一交易日执行日期严格分离；按下一交易日开盘价、交易单位和停牌状态执行；无当日行情的持仓用最近收盘价估值并标记stale。
- ETF分红：按登记日持仓份额确定权益，在派息日计入现金账本，分红不计为外部投入。
- 信号到订单：按信号日收盘价估算整手数量，下一交易日按真实开盘价执行；跳空造成资金不足时拒绝成交。
- 费用模型：佣金、其他费用、最低佣金和货币精度显式配置，不把未核验费率写成默认事实。
- 公共资金池：按%B偏离程度排序，执行最低现金储备和单只ETF市值上限；可根据指数成分与行业映射限制新增资金分配。
- 行业暴露硬门禁：缺少成分穿透或行业分类时拒绝计算，不静默忽略。
- 策略信号：固定定投、布林下轨四档单周期触发、S0持有/S1上轨卖出/S2回归通道后分两次卖出。
- 绩效基础：账户市值、剔除期末外部投入影响的单位净值、最大回撤。

### 尚未完成

- 用户本机 free-stockdb 服务与真实数据覆盖探测；
- 分红事件数据源及逐笔核验；
- 历史指数成分和历史权重数据源；
- 接入真实交易日历数据并对五只ETF逐只完成缺口审计；
- 涨跌停、买卖价差、滑点、价格冲击及券商最低收费的真实执行规则；
- 公共现金池与行业穿透暴露上限的组合约束；
- 完整A/B/C/D策略编排、卖出S0/S1/S2对照和分配周期状态管理；
- 完整账户估值、收益、回撤、滚动区间与参数稳健性报告。

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

1. 在用户本机运行free-stockdb探测脚本，确认五只ETF真实覆盖、因子数量和OHLC质量。
2. 核验交易日历、ETF分红公告、历史指数成分/权重来源及其授权。
3. 完成涨跌停、滑点、价差和券商费用规则的成交模拟。
4. 补齐A/B/C/D完整策略编排、资金流收益计算和滚动/敏感性报告。
5. 以审计通过的真实数据运行历史回测；在此之前不输出真实策略收益结论。
