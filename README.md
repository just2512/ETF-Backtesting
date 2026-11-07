# ETF-Backtesting

面向场内 ETF 长期积累策略的可复现研究与回测项目。

## 当前研究目标

验证多只 ETF 共用公共现金池、各自独立持仓账本的长期积累策略，重点比较：

- 固定周期定投；
- 布林下轨分批买入、不主动卖出；
- 布林下轨买入、上轨分批卖出；
- 布林信号驱动的公共资金池动态分配，并保留长期底仓。

本项目首先验证数据是否足以支持可信回测。数据不完整时，必须输出 `MISSING` 或 `UNKNOWN`，不得用模拟数据冒充真实历史结果。

## 初始 ETF 研究池

| 代码 | 产品 | 研究角色 | 状态 |
|---|---|---|---|
| 510300 | 沪深300ETF | A股宽基 | 候选 |
| 510880 | 上证红利ETF | 红利/价值 | 候选 |
| 513020 | 港股通科技ETF | 港股科技成长 | 候选 |
| 159928 | 中证主要消费ETF | 主要消费 | 候选 |
| 159611 | 中证全指电力公用事业ETF | 电力公用事业 | 候选 |

上述是研究候选池，不代表最终必须全部纳入。159611 与 561560 属于同指数产品备选，首轮只选其一；煤炭ETF暂不纳入核心池。产品代码、跟踪指数、上市日期、规模、流动性和费率均须在数据审计阶段重新核验。

## 配置模板

- [ETF候选池](config/etf_universe.yaml)
- [数据源配置](config/data_sources.yaml)
- [回测参数](config/backtest.yaml)
- [交易费用模板](config/trading_costs.yaml)（待券商规则核实）

## 设计文档

- [总体架构](docs/ARCHITECTURE.md)
- [数据契约](docs/DATA_CONTRACT.md)
- [数据审计计划](docs/DATA_AUDIT_PLAN.md)
- [外部历史数据源候选](docs/DATA_SOURCE_OPTIONS.md)
- [指数重叠方法](docs/OVERLAP_METHODOLOGY.md)
- [回测方法](docs/BACKTEST_METHODOLOGY.md)
- [验收标准](docs/ACCEPTANCE_CRITERIA.md)
- [实施与并行开发计划](docs/WORK_PLAN.md)

## 数据源边界

支持两种 free-stockdb 接入形态：本机 LevelDB 服务（本地适配器）与用户提供的远程 `stock_sdk` 双端服务（远程适配器）。远程日线通过在线 `get_price(..., fq=None)` 读取不复权 OHLCV；交易日历与历史指数快照走对应在线 API。原生 `rd.get()` 是独立可选通道，原生端口不可用不得阻断在线回测。在线财务与 Tick 仅作为补充数据。服务地址通过环境变量配置，不写入仓库。项目不假定任一服务已具备完整历史数据、有效复权因子、分红事件或历史指数成分权重；必须先运行本机覆盖探测并核验字段和数据语义。详见 [数据源审计](docs/FREE_STOCKDB_SOURCE_AUDIT.md)。

远程 SDK 覆盖探测（在安装了 `stock_sdk` 的本机执行）：

```powershell
$env:STOCKSDK_HOST = "<init() 使用的主机>"
$env:STOCKSDK_PORT = "7899"
$env:STOCKSDK_ONLINE_ENDPOINT = "<set_init() 使用的 host:port>"
python scripts/probe_stock_sdk.py
```

远程历史数据快照导出（仅访问在线 API，不读取本地 LevelDB）：

```powershell
$env:STOCKSDK_HOST = "106.75.217.246"
$env:STOCKSDK_PORT = "7899"
$env:STOCKSDK_ONLINE_ENDPOINT = "106.75.217.246:12328"
python scripts/export_remote_history.py
```

默认将五只候选 ETF 的不复权日线写入 `data/snapshots/remote-stock-sdk/`，并生成包含每只证券记录数、首末日期、SHA-256 和交易日历缺口的 `manifest.json`。某只 ETF 拉取失败不会丢弃其他成功结果；空交易日历或日历接口异常必须标记 UNKNOWN。数据快照目录已被 Git 忽略。日历缺口暂标记为 UNKNOWN，因为缺少逐证券停牌状态时不能把缺K线直接判定为数据错误或停牌。

历史指数成分/权重快照导出（权重字段和单位必须先从 SDK 实际返回值确认，禁止自动猜测）：

```powershell
python scripts/export_index_history.py --index-id 000300.XSHG --dates 2020-06-30 2021-06-30 --symbol-field <实际证券代码字段> --weight-field <实际权重字段> --weight-scale percent
```

若 API 返回的权重是 0.0–1.0 的小数比例，将 `--weight-scale` 改为 `fraction`。导入器会拒绝字段缺失、成分重复、非正权重和权重合计不在 100% 容差内的数据；不会把不完整成分列表自动归一化。每个历史日期独立写 CSV 与 SHA-256，失败日期保留在 manifest 中。

## 关键原则

1. 信号计算与成交执行分离：收盘后生成信号，下一交易日按可成交价格执行。
2. 真实成交使用 ETF 未复权市场价格；分红、拆分等公司行为通过独立账本处理。
3. 不得将当前指数成分股回填到历史日期。
4. 所有策略共用同一成交引擎、费用模型、现金池和持仓账本。
5. 原始行情与本地数据快照不提交 GitHub；仓库只保存代码、配置模板、文档和小型测试 fixture。
6. 不对历史回测结果作收益承诺，不以单一历史区间或单一参数作为结论。

## 项目状态

设计基线与四条首轮工作线已合并到 `main`。当前已实现数据适配/审计基础、指数重叠计算、布林指标和现金账本基础；真实本地数据覆盖、分红、历史指数成分、成交引擎、公共资金池及完整策略仍在实施。详见 [实施状态](docs/IMPLEMENTATION_STATUS.md) 和 [free-stockdb静态审计](docs/FREE_STOCKDB_SOURCE_AUDIT.md)。
