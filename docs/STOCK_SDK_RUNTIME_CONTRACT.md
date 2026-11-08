# stock_sdk 实际运行时契约（2026-11-08 本机实测）

本文件由 Jerry 本机（Python 3.12.10，`D:\stockdb\pybao`）对**实际安装的 stock_sdk 模块**和真实远程服务探测生成，供云端适配器对齐，替代对公开仓库源码的推断。机器可读版：`reports/audit/remote_sdk_contract.json`（本地，不入库）。

## 模块身份

| 项 | 值 |
|---|---|
| `stock_sdk.__file__` | `D:\stockdb\pybao\stock_sdk.py`（Python 封装层） |
| 底层二进制 | `D:\stockdb\pybao\stockdb.pyd`（RemoteProxy 由它注入） |
| 模块级可调用 | 72 个 |

## 函数签名（inspect 实测）

| 函数 | 实际签名 |
|---|---|
| `init` | `(host: str = '127.0.0.1', port: int = 7899, socket_timeout: Optional[int] = None, password: Optional[str] = None, warm: bool = True)` |
| `set_init` | `(ip='', df=None, cpu=None)` — **`df` 是持久化模式开关** |
| `get_price` / `get_bars` / `get_trade_days` / `get_index_stocks` / `get_index_weights` / `get_history_constituents` / `get_last_tick` / `get_security_info` / `get_extras` | 均为 `RemoteProxy`（无 Python 签名，转发到在线服务） |
| `get_fundamentals` | `(query_object, date=None, statDate=None)` |

## 在线 API 真实行为（与公开文档/源码的差异，逐条实测）

1. **日期格式**：`get_trade_days(start_date=..., end_date=...)` 传 `YYYYMMDD` **静默返回 `[]`**（无报错）；传 `YYYY-MM-DD` 正常。`get_price` 两种格式当时都能收（服务端故障期间无法二次确认，云端调用应统一用短横线）。**适配器已在 `read_trade_days` 内部把 8 位日期转为短横线**。
2. **`get_price` 列表模式丢日期**：`set_init` 未开 `df=True` 时，`get_price` 返回 `[{'open': ..., 'close': ...}]`，**没有 date 字段**——多日历史无法定位行。官方文档 §12.2 明确：`df=True` 返回 pandas.DataFrame、日期在索引。**适配器已在 `read_daily_bars` 前强制 `set_init(endpoint, df=True)`**。
3. **服务端故障返回错误字符串而非异常**：故障期 `get_price/get_bars/get_index_stocks/get_index_weights/get_security_info/get_last_tick` 全部返回裸字符串 `"\n执行查询时发生错误"`（Unicode: U+6267 U+884C U+67E5 U+8BE2 U+65F6 U+53D1 U+751F U+9519 U+8BEF），不抛异常。**适配器已把字符串识别为 ConnectionError，携带原文**。
4. **复权语义**（2026-11-07 锚点实测，`get_price` 服务健康时）：`fq=None` 与本地 LevelDB 不复权逐位一致（510300@2024-01-02 open=3.502/close=3.453）；`get_bars` **默认复权**（同锚点 close=3.265）。
5. **`get_index_stocks/get_index_weights`**：需 `.XSHG` 后缀；`date=` 参数为真历史时点（2020-06-30 vs 当前快照成分进出各 104 只，2026-11-07 实测）。

## 服务状态事件（2026-11-08 探测时点）

| 能力 | 状态 |
|---|---|
| `get_trade_days` | PASS（43 交易日，2020-06-01~07-31） |
| `get_price` / `get_bars` | 服务端故障，返回错误字符串 |
| `get_index_stocks` / `get_index_weights` | 服务端故障 |
| `get_last_tick` / `get_security_info` / `get_all_securities` | 服务端故障 |
| K线库 7899 | 拒绝连接 |
| 7898 | TCP 通，非 K 线库协议（`Invalid data length`） |

2026-11-07 同一时段上述故障 API 曾全部正常（tick/price/bars/index 均有真实返回），故障是**供应商服务端波动**，不是接口契约消失。日历 API 在两轮探测中均可用。

## 对云端的结论

- 云端模拟测试无法连接 `106.75.217.246` 属实；本文件即从真实环境取得的 SDK 契约与样本（结构见 JSON）。
- 适配器三个契约缺陷（日期格式/df 模式/错误字符串）已在本轮修复并有单测覆盖；等 `get_price` 服务恢复后重跑 `scripts/export_remote_history.py` 即可产出五只 ETF 真实快照。
- 快照数据文件不入库（`data/snapshots/` 已 gitignore）；manifest 的 SHA-256 机制保持完整。
