# free-stockdb 用户 fork 源码审计（静态审计）

审计对象：`just2512/free-stockdb` 的 GitHub `main` 分支源码。此报告只描述仓库中可见的源码、配置和文档，不代表访问了用户 Windows 本机的数据目录或运行中的 StockDB 服务。

## 可确认的能力

| 项目 | 静态审计结果 | 证据范围 |
|---|---|---|
| 日K / 分钟K | PASS（接口能力） | Python SDK 的 `get_data` 支持日线和分钟线查询 |
| 周K / 月K | PASS（接口能力） | SDK 可由日K聚合生成 |
| 原始行情查询 | PASS（接口能力） | `fq=None` 可请求不复权行情 |
| 前复权 / 后复权 | PASS（接口能力，语义待验证） | SDK 实现 `qfq` / `hfq`，并从 `复权*` 预载 `cum` |
| ETF历史覆盖 | UNKNOWN | 仓库未包含本地LevelDB行情文件，不能证明五只ETF实际有数据 |
| 分红现金流明细 | MISSING | 已检查的公开SDK和仓库文档未发现可用的分红事件读取接口 |
| 带生效日期的指数历史成分/权重 | MISSING | 已检查的公开SDK和文档未发现历史成分及权重接口 |
| 当前行业/板块映射 | PASS（能力） | README示例存在 `bk.get`，但不等价于历史指数成分 |

## 重要实现风险

SDK 的 `StockDBClient` 会尝试读取 `复权*` 表并构造 `_fq_dates` / `_fq_cums`。但初始化时相关读取异常会被吞掉；后续 `_apply_fq_in_memory` 在某证券没有因子记录时直接返回原始记录。因此，调用者指定 `fq="qfq"` 并不能单独证明返回值已经完成前复权。

本项目适配器因此：
- 成交模拟明确请求 `fq=None`；
- 将因子记录单独暴露，不推断累计因子的方向或生效语义；
- 不把缺少因子解释成“没有公司行为”；
- 不伪造分红或历史指数成分数据。

## 数据目录和同步配置

- 仓库 `.gitignore` 明确忽略 `data/` 和 `*.ldb`，所以行情数据库不会出现在 GitHub 文件树。
- `sync_url.txt` 当前只有注释示例，没有有效同步源配置。
- `stockdb.conf` 默认本机服务地址为 `127.0.0.1:7899`。
- 数据源文档说明同步器从有效配置读取镜像根目录，并使用 `manifest.txt` 校验 SHA-256 和文件大小。

因此，静态审计无法取得真实覆盖日期、交易日数量、复权因子数量或五只ETF的分红记录。

## 必须在用户本机完成的验证

在已安装 free-stockdb Python SDK、数据服务已启动的机器上运行：

```powershell
python -m pip install -e .
$env:PYTHONPATH = "C:\\path\\to\\free-stockdb\\pybao;$env:PYTHONPATH"
$env:FREESTOCKDB_HOST = "127.0.0.1"
$env:FREESTOCKDB_PORT = "7899"
python scripts/probe_free_stockdb.py --output reports/audit/free_stockdb_probe.json
```

若 SDK 不在 Python 模块搜索路径中，应先按 free-stockdb 自带安装说明配置 Python 环境；不要把密码写入仓库或命令历史。探测JSON包含行情覆盖摘要、OHLC质量检查和复权因子状态。若无权威交易日历，交易日完整性会保持UNKNOWN。将生成的 JSON 结果保存到本地并提供给项目审计流程。

## 本机探测结果（2026-11-07）

在 Jerry 本机（Python 3.12.10，`stockdb.exe` 运行于 127.0.0.1:7899，`pybao` 已在 Python 路径）执行：

```
PYTHONPATH="src;D:\stockdb\pybao" python scripts/probe_free_stockdb.py --output reports/audit/free_stockdb_probe.json
```

退出码 0；JSON 保存在本地 `reports/audit/free_stockdb_probe.json`（已被 .gitignore 排除，不入库）。

| 代码 | 名称 | 上市/应当有数据的起始 | 日线根数 | 首日 | 末日 | 复权因子数 |
|---|---|---:|---|---:|---:|---:|
| 510300 | 沪深300ETF | 2012 | 688 | 2024-01-02 | 2026-11-06 | 14 |
| 510880 | 上证红利ETF | 2007 | 4811 | 2007-01-18 | 2026-11-06 | 19 |
| 513020 | 港股通科技ETF | 2022 | 1152 | 2022-02-08 | 2026-11-06 | 0 |
| 159928 | 中证主要消费ETF | 2013 | 688 | 2024-01-02 | 2026-11-06 | 1 |
| 159611 | 中证全指电力公用事业ETF | 2022 | 1169 | 2022-01-07 | 2026-11-06 | 0 |

OHLC/重复日期/字段完整性：五只全部 PASS，无 REJECT；交易日历缺口仍 UNKNOWN（无权威日历）。

关键发现：

1. **510300 与 159928 的日线仅从 2024-01-02 起（各 688 根），历史严重不全**——两只 ETF 分别于 2012/2013 上市，却只有约 2.85 年日线。`510880` 却完整到 2007 年。这是数据同步/数据源历史窗口问题，不是 SDK 查询问题（`fq=None` + 无日期范围即查全量）。在做长周期回测前必须重跑 `数据更新.exe` 补齐全史，或确认数据源是否只提供近三年日线。
2. **513020 与 159611 复权因子数为 0，159928 仅 1 条**。因子为 0 不等价于"无公司行为"——也可能是新 ETF 尚未分红；适配器按约定保守标记 `MISSING`，不做"无分红"推断，需对照交易所除权除息公告独立核验后再决定是否放行 `qfq` 指标。
3. 复权因子语义（累计方向/除权日对齐）仍未对照权威公告核验，保持 `UNVERIFIED`。
4. 现金分红事件、带生效日期的历史指数成分/权重接口仍 `MISSING`。

## 当前审计结论

- 行情接口能力：PASS（本机 127.0.0.1:7899 实测可读五只ETF日线）
- 用户本地五只ETF实际行情覆盖：已探测，510880/513020/159611 覆盖完整，510300/159928 仅 2024 年起、历史不全
- 复权因子实际覆盖：已探测（14/19/0/1/0），语义仍 UNVERIFIED
- 分红现金事件接口：MISSING（当前已检查的公开SDK）
- 历史指数成分及权重接口：MISSING（当前已检查的公开SDK）

在补齐 510300/159928 全史、核验复权因子语义并接入分红/历史指数数据前，不启动真实历史回测，不以当前行业板块映射替代历史指数成分。


## 新增远程 stock_sdk 接口线索（2026-11-07）

用户补充了远程双端初始化示例：init(host, port) 与 set_init(host:port)，以及原生 rd.get("日k", symbol, start>end)、在线 get_fundamentals(...) 和 get_last_tick(...)。公开的 free-stockdb Python 示例也展示了 rd.get_data(..., frequency="1d", fq=None) 的不复权读取方式。项目已新增独立 StockSDKAdapter，避免把该远程入口与本机 LevelDB 端口混为一谈。

当前边界：
1. 用户给出的远程服务地址没有在 GitHub Actions 环境中进行网络连接测试；不能把适配器的模拟测试当作真实服务联通证据。
2. 适配器使用 rd.get_data 的标准化记录读取 OHLCV；原生 rd.get("日k", ...) 仍原样返回，等待本机输出字段结构核验。
3. 在线财务查询和 Tick 是补充数据，不构成历史 ETF 日线。
4. 公开页面提及指数数据能力，但尚未确认可调用函数、指数覆盖清单、权重单位、公布日期与历史有效日期语义；历史指数成分/权重状态维持 UNKNOWN，禁止用最新快照回填历史。
5. 分红事件接口与复权因子语义同样未完成字段级及事件级验证，维持 UNKNOWN / UNVERIFIED。

本机验证可通过 StockSDKAdapter.from_environment() 初始化，并对 510300、510880、513020、159928、159611 调用 probe_universe()。服务地址只通过环境变量配置：STOCKSDK_HOST、STOCKSDK_PORT、STOCKSDK_ONLINE_ENDPOINT；不要提交真实地址或凭据到仓库。


### stock_sdk 本机覆盖探测命令

在安装了 SDK 的 Windows 环境中，先配置双端地址（值沿用用户本机实际可用的 init() 与 set_init() 参数；不要将其写入仓库）：

```powershell
$env:STOCKSDK_HOST = "<init() 使用的主机>"
$env:STOCKSDK_PORT = "7899"
$env:STOCKSDK_ONLINE_ENDPOINT = "<set_init() 使用的 host:port>"
python scripts/probe_stock_sdk.py --output reports/audit/stock_sdk_probe.json
```

脚本默认探测 510300、510880、513020、159928、159611；可用 --symbols 覆盖。JSON 会记录每只 ETF 的观察到的日线根数、首末日期和 OHLC 审计结果。交易日历完整性、复权因子语义、分红事件与历史指数成分/权重不会因为接口连通而自动变成 PASS，仍按 UNKNOWN / UNVERIFIED 保留。`reports/audit/` 已在 .gitignore 中排除，不会把本地数据报告提交到 Git。


## 远程在线 API 实测记录（2026-11-07）

以下为用户在可访问远程 SDK 的运行环境提供的实测结果；这是远程服务侧实测记录，不是 GitHub Actions 或本执行环境的联网结果。该数据链路不读取本地 LevelDB：

| ETF | 在线不复权日线根数 | 首个交易日 | 结论 |
|---|---:|---|---|
| 510300 | 3510 | 2012-05-28 | 全史覆盖至探测日 |
| 510880 | 4811 | 2007-01-18 | 全史覆盖至探测日 |
| 513020 | 1152 | 2022-02-08 | 全史覆盖至探测日 |
| 159928 | 3192 | 2013-09-16 | 全史覆盖至探测日 |
| 159611 | 1169 | 2022-01-07 | 全史覆盖至探测日 |

远程在线行情使用 `get_price(..., fq=None)`。已报告的锚点与本地不复权价格一致；`get_bars` 默认复权价不得作为成交价格。以上在线数据覆盖结论不依赖本地 LevelDB 是否完整。

其他在线接口实测：

- `get_trade_days`：PASS，可读取交易日历。
- 历史指数成分/权重：PASS；指数代码需使用交易所后缀（例如 `.XSHG`），并传入历史 `date`。2020-06-30 与当前快照比较，成分进出各 104 只，且权重日期/数值不同，支持其为历史时点快照而非当前成分回填。
- ETF现金分红事件：MISSING。`get_fund_info` 调用持续报错；前/后复权价差推断出现 70 个假阳性日期，明确禁止作为分红事件源。
- 原生 K 线端口 7899：此前远程探测为拒绝连接；7898 协议不匹配。在线 API 12328 可用。原生端口失败不能作为在线 API 不可用的证据。

### 对回测门禁的影响

1. 远程不复权日线覆盖门禁：按上述用户实测结果可记为远程数据源 PASS；每次正式回测仍需保存本次拉取的实际记录数、首末日期、数据哈希和获取时间。
2. 交易日历门禁：接口可用，但五只ETF逐日缺口审计仍需在实际导入的数据上执行，区分未上市日期、停牌日期与异常缺失。
3. 历史指数成分门禁：历史成分快照接口可用；历史权重字段单位、权重归一、有效日期与公布日期仍须由导入器验证后，才能放行行业暴露约束。
4. 分红门禁：仍 BLOCKED。未取得官方分红公告事件前，不得把现金分红设为零，也不得将复权价差转换为现金分红。
5. 成交规则门禁：涨跌停、停牌可成交状态、买卖价差、滑点、价格冲击和券商最低收费尚未全部核验；未完成前只能输出明确标记的简化成交实验，不得称为完整实盘约束回测。


## 远程在线 API：数据导入器与权重语义门禁（2026-11-07）

远程在线 API 已由用户实测可读取历史指数成分/权重快照，但仅凭接口返回成功，不能确认权重字段是 0–1 还是 0–100，也不能确认是否完整覆盖全部成分。项目新增：

- `src/etf_backtesting/data/index_history.py`：历史快照规范化与导出。
- `scripts/export_index_history.py`：按指数代码和历史日期逐次调用远程接口。
- `tests/data/test_index_history.py`：覆盖日期绑定、fraction/percent显式单位、重复证券、缺字段、权重不归一、逐日期失败隔离和快照哈希。

导入器要求调用者显式提供真实返回字段名及权重单位。它不会根据 0.25 猜测 25% 或 0.25%，也不会把不完整权重列表自动缩放到100%。只有权重总和在显式容差内（默认0.5个百分点）才允许标记 PASS。当前仍未获得远程 SDK 的真实原始返回样本，因此字段名与单位尚不能在本次代码侧独立确认；真实导入门禁仍为 UNKNOWN，行业暴露约束不得因此自动放行。

命令示例（尖括号内容必须替换为 SDK 返回的实际字段名）：

```powershell
python scripts/export_index_history.py --index-id 000300.XSHG --dates 2020-06-30 2021-06-30 --symbol-field <实际证券代码字段> --weight-field <实际权重字段> --weight-scale percent
```

`weight-scale` 只能显式选 `fraction` 或 `percent`。导出 manifest 保存查询日期、字段映射、单位、权重合计、证券数量和 SHA-256；单个日期失败不会抹掉其他成功日期。


## 精确远程 SDK 契约探测

公开的 `just2512/free-stockdb/pybao/stock_sdk.py` 当前是 class-based `StockDBClient` 接口，文件顶部导入 `stockdb.init/rd`，没有定义用户 `sdk_test.py` 示例中的模块级 `set_init/get_price/get_fundamentals/get_last_tick`。因此不能把该公开文件直接当作用户运行环境中实际使用的模块，也不能在 GitHub Actions 中擅自用它替代。

新增 `scripts/probe_remote_sdk_contract.py`，在配置了用户实际 `./pybao/` 的 Python 环境中运行：

```powershell
$env:PYTHONPATH = ".\\pybao;$env:PYTHONPATH"
$env:STOCKSDK_HOST = "106.75.217.246"
$env:STOCKSDK_PORT = "7899"
$env:STOCKSDK_ONLINE_ENDPOINT = "106.75.217.246:12328"
python scripts/probe_remote_sdk_contract.py --index-id 000300.XSHG --date 2020-06-30
```

探测文件 `reports/audit/remote_sdk_contract.json` 会记录真实导入模块路径、函数签名、历史指数返回的字段名/数据类型/样例行、数值列范围/合计及交易日历样本。它不会根据列名猜权重单位，也不会把当前成分当作历史成分。只有拿到该原始输出，才能把 `--symbol-field`、`--weight-field` 和 `--weight-scale` 填入 `scripts/export_index_history.py` 并生成可审计快照。


## 官方ETF分红数据门禁

新增 `scripts/import_dividends.py`，输入为两份由官方公告整理的CSV：

1. 事件表：每次分红的除息日、登记日、派息日、每份分红金额、公告日期、公告URL。
2. 覆盖表：每只ETF的官方来源及覆盖起止日期。

五只ETF必须全部声明覆盖整个回测区间。没有事件记录但覆盖声明完整，才可表示该区间未发现分红；缺失覆盖声明一律 UNKNOWN。事件公告URL必须为白名单域名下的HTTPS地址，公告日期不能晚于除息日。两份CSV生成组合SHA-256，正式策略运行必须传入该哈希。当前未取得实际官方公告CSV，分红门禁仍 MISSING。


## 对照公开 sdk_test.py 的K线调用

已检查 `调用方式/python/sdk_test.py`：其批量历史日线示例调用 `rd.get_data(hs[:3], start="20260713", end="20260715", frequency="1d", fq="qfq")`，注释明确 `fq=None` 表示不复权；用户给出的远程启动示例另使用 `rd.get("日k", code, range)` 做毫秒级范围查询。

适配器支持两种历史路径：
- 如果运行时模块导出 `get_price`，优先调用该在线接口并传 `fq=None`。
- 否则尝试 `rd.get_data(code=..., start=..., end=..., frequency="1d", fq=None, as_df=True)`。只有原生通道初始化成功时才调用；7899拒连时不将其伪装成12328在线行情。

`scripts/probe_remote_sdk_contract.py` 现在会同时记录模块级函数签名和 `rd.get/rd.get_data` 签名。公开SDK源码与用户当前实际运行模块是否相同，仍以探测输出的 `sdk_module_file` 为准。


## 历史指数双接口调用路径修正

PR #22 的本机实测记录明确给出了实际历史接口名：`get_index_stocks` 与 `get_index_weights`，两者都需要指数交易所后缀及 `date` 参数。之前代码只假设单一 `get_history_constituents`，与该实测记录不一致。

现已修正：
- 默认分别调用 `get_index_stocks(index_id, date=...)` 和 `get_index_weights(index_id, date=...)`。
- 将股票代码列表与权重记录按证券代码严格合并；重复代码、缺失权重、额外权重均 REJECT。
- 若运行时确实提供单一组合接口，可通过 `STOCKSDK_INDEX_API` 显式指定。
- `scripts/probe_remote_sdk_contract.py` 同时探测两个接口的原始结构；权重字段与单位仍需根据实际返回样本显式指定。
