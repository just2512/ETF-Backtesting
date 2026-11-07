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
$env:FREESTOCKDB_HOST = "127.0.0.1"
$env:FREESTOCKDB_PORT = "7899"
python scripts/probe_free_stockdb.py
```

若 SDK 不在 Python 模块搜索路径中，应先按 free-stockdb 自带安装说明配置 Python 环境；不要把密码写入仓库或命令历史。将生成的 JSON 结果保存到本地并提供给项目审计流程。

## 当前审计结论

- 行情接口能力：PASS
- 用户本地五只ETF实际行情覆盖：UNKNOWN
- 复权因子实际覆盖与语义：UNKNOWN
- 分红现金事件接口：MISSING（当前已检查的公开SDK）
- 历史指数成分及权重接口：MISSING（当前已检查的公开SDK）

在本机探测报告返回前，不启动真实历史回测，不以当前行业板块映射替代历史指数成分。
