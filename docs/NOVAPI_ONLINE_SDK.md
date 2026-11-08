# NovAPI online stock_sdk integration

The historical market-data provider is the NovAPI online API documented at
https://dns.novapi.cc/docs/index.html. It is not the free-stockdb local HTTP
query endpoint.

## Cloud initialization

The cloud runner imports the provider's official `stock_sdk` module and calls
`set_init("106.75.217.246:12328")`. The native local StockDB channel
(`init(host, 7899)`) is independent and is skipped by default. It can be
explicitly enabled with `STOCKSDK_INIT_NATIVE=true` only for jobs that really
need the local `rd` channel.

Configuration:
- `STOCKSDK_MODULE=stock_sdk` (default)
- `STOCKSDK_ONLINE_ENDPOINT=106.75.217.246:12328` (default; override if provider changes it)
- `STOCKSDK_INIT_NATIVE=false` (default)

## Required APIs and semantics

- `get_price(symbol, start_date, end_date, frequency="daily", fq=None)`: unadjusted historical daily prices.
- `get_trade_days(start_date, end_date)`: authoritative exchange trading sessions. Send dashed ISO dates (`YYYY-MM-DD`); compact `YYYYMMDD` has been observed to return an empty list silently.
- `get_index_stocks(index_id, date=...)` and `get_index_weights(index_id, date=...)`: historical index membership and weights. Use the provider's exchange suffix, e.g. `.XSHG`, and preserve the requested historical date.

The adapter enables DataFrame mode before `get_price` because list mode omits
the date field. Provider error strings such as `执行查询时发生错误` are
converted to connection errors while retaining the original text; they are
retryable by the existing exporter policy. Empty results remain MISSING, not
successful imports.

## Runtime dependency

The provider SDK includes a platform-specific native extension. The Python
module alone from the public free-stockdb local-engine repository is not a
substitute for the NovAPI-enabled SDK build: that source module only wraps
local `stockdb` and does not expose the online RemoteProxy methods. Cloud
runners must install the official Linux-compatible SDK distribution that
contains the same `RemoteProxy` API as the user's tested runtime. Do not
silently fall back to the local HTTP SDK or to mock responses.

## Acceptance boundary

This repository has the correct cloud-side provider selection and adapter
contract. Actual data import is PASS only after the cloud job imports the
official SDK binary, reaches the provider endpoint, and writes audited
historical responses for all five ETFs plus dated index constituent/weight
snapshots. A green mocked CI test does not prove provider availability.
