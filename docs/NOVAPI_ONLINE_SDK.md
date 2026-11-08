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
the date field. Generic provider error strings such as `执行查询时发生错误` are
converted to connection errors while retaining the original text and retried.
The live cloud run also exposed the provider's explicit test-quota response:
`测试期超2000次…24小时内会重置`. This is classified as a non-retryable
`ProviderQuotaExceeded`; the exporter stops issuing further calls instead of
burning the remaining quota. Empty results remain MISSING, not successful imports.

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


## Request-volume boundary and index snapshot cadence

The provider explicitly warns that the online API is a supplemental source,
not a bulk-download interface, and directs unlimited batch queries to local
StockDB. The current test service enforces a 2,000-request quota with a
24-hour reset. Therefore the cloud workflow does not issue daily historical
index requests. It imports the first available session from the common
2022-02-08 start plus each month's final trading session plus the latest available session for the five tracking
indices. This is a point-in-time monthly snapshot series suitable for monthly
rebalance analysis; it does **not** establish daily index-constituent coverage.
The manifest records `MONTH_END_PLUS_RANGE_START_AND_LATEST` and keeps daily completeness
UNKNOWN. A full daily index history requires the provider's bulk/local StockDB
data path or a separately authorized bulk mirror; the online supplement API
must not be used to bypass its stated limit.
