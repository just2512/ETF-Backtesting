# 本地 StockDB 回测准备与执行

本方案与 NovAPI 云端导入完全分离。本地导出脚本只连接 `FREESTOCKDB_HOST:FREESTOCKDB_PORT` 上的 free-stockdb 服务，不调用 `set_init()`、不访问 NovAPI，也不把云端快照回填成本地数据。

## 1. 本机环境准备

在 Windows PowerShell 中进入仓库目录，确认：

- free-stockdb 的本地服务已启动，默认监听 `127.0.0.1:7899`；
- 与该服务版本匹配的 Python SDK `stock_sdk.StockDBClient` 已安装或加入 `PYTHONPATH`；
- Python 版本满足项目要求（Python 3.11+）。

按实际安装位置设置 SDK 路径（如果已安装到当前 Python 环境，可跳过）：

```powershell
$env:PYTHONPATH = "D:\\stockdb\\pybao;$env:PYTHONPATH"
$env:FREESTOCKDB_HOST = "127.0.0.1"
$env:FREESTOCKDB_PORT = "7899"
# 如服务设置了密码，再设置；不要把密码写入仓库或命令历史
# $env:FREESTOCKDB_PASSWORD = "<本机服务密码>"

python -m pip install -e ".[dev]"
```

先做只读覆盖探测：

```powershell
python scripts/probe_free_stockdb.py --output reports/audit/free_stockdb_probe.json
```

## 2. 导出本地五只 ETF 不复权全史

```powershell
python scripts/export_local_history.py --start 20000101 --end (Get-Date -Format yyyyMMdd)
```

默认输出到 `data/snapshots/local-stockdb/`：

- `510300.csv`、`510880.csv`、`513020.csv`、`159928.csv`、`159611.csv`；
- `manifest.json`：来源、请求区间、逐标的根数、首末日期、SHA-256、质量审计和缺失门禁；
- 行情均为原始不复权 OHLCV（`fq=None`），用于成交价格输入。

数据目录已被 `.gitignore` 排除，不会提交到 GitHub。脚本只读本地 StockDB 并写出快照，不修改 StockDB 原始数据库。

退出码：
- `0`：保留给所有扩展验收门禁均通过的完整实现；当前本地适配器没有权威交易日历/停牌状态/分红事件/历史指数数据，因此不会返回 0。
- `3`：至少一只 ETF 无行情；
- `4`：数据已导出，但仍有 UNKNOWN 门禁（当前预期）；
- `5`：发现明确的数据结构或价格记录错误。

## 3. 必须核验的本地历史覆盖

不要只看 CSV 是否生成。逐只检查 manifest：

| ETF | 已知上市首日 | 先前本机探测情况 |
|---|---|---|
| 510300 | 2012-05-28 | 先前只有 2024-01-02 起的 688 根，必须补齐 |
| 510880 | 2007-01-18 | 先前覆盖到 2007-01-18 |
| 513020 | 2022-02-08 | 先前覆盖到 2022-02-08 |
| 159928 | 2013-09-16 | 先前只有 2024-01-02 起的 688 根，必须补齐 |
| 159611 | 2022-01-07 | 先前覆盖到 2022-01-07 |

“先前本机探测”来自 2026-11-07 的静态审计记录，不代表当前数据库状态。此次导出结果才是当前证据。如果 510300 或 159928 仍从 2024 年开始，先通过 free-stockdb 正规数据更新流程补齐，再重新导出；不要用 NovAPI 云端结果悄悄拼接本地序列。

首日匹配只证明观察到的首个日期符合已知上市日期，不能证明中间没有缺日。当前本地 SDK 适配器没有权威交易日历和逐证券停牌状态，因此 `calendar_completeness` 始终为 `UNKNOWN`，不能将它解释成全史完整。

## 4. 本地方案当前无法从 free-stockdb 自动提供的输入

- ETF现金分红事件及逐只覆盖证明：`MISSING`。没有官方公告事件文件前，不能假设分红为零。
- 历史指数成分与权重：本地 SDK 当前未暴露带日期的历史成分权重接口，标记 `MISSING`。不能拿当前板块映射替代历史指数。
- 历史报价、涨跌停/停牌状态、价差、滑点和价格冲击：没有完整历史数据前，正式成交模型门禁仍未通过。
- 复权因子：即使存在，也必须独立核验因子方向和生效日期；成交仍使用不复权价格。

因此，本地导出脚本是数据准备与审计入口，不会自行启动正式回测，也不会把未满足门禁的结果标记为正式回测。可在满足上述数据门禁后，将本地 CSV 快照与 manifest 哈希交给统一回测入口。

## 5. 云端与本地数据隔离

| 项目 | 云端方案 | 本地方案 |
|---|---|---|
| 行情来源 | NovAPI 在线 `get_price(fq=None)` | 本机 free-stockdb `StockDBClient.get_data(fq=None)` |
| 服务端配额 | 受 NovAPI 在线调用限额约束 | 不消耗 NovAPI 在线配额 |
| 历史指数 | NovAPI 日期快照导入器 | 当前本地 SDK 不提供 |
| 输出目录 | `reports/novapi/`、`data/snapshots/remote-stock-sdk/` | `data/snapshots/local-stockdb/` |
| 数据混用 | 禁止自动回退 | 禁止自动拼接云端数据 |

两套快照分别保存来源、获取时间和哈希。若研究中需要比较两套数据，必须先做显式逐日差异审计，不得静默合并。
