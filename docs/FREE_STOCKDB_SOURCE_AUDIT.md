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
