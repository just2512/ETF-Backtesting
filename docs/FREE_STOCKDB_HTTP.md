# free-stockdb HTTP data source

ETF-Backtesting includes an HTTP-only client for a self-hosted free-stockdb
server. It does not import the upstream native \`stockdb.pyd\` extension.

Configure \`STOCKSDK_MODULE=etf_backtesting.adapters.free_stockdb_http_sdk\`
and \`STOCKSDK_ONLINE_ENDPOINT\` as the HTTPS reverse-proxy URL for the server.
The current adapter factory also requires \`STOCKSDK_HOST\`; the HTTP-only
module accepts that compatibility argument but does not open a native socket.

The client uses the documented \`/?cmd=get&t=日k:<symbol>:*\` prefix query and
filters dated keys locally. The server must include the URL-decoding fix in
\`just2512/free-stockdb\` branch \`work/http-query-decoding\`; without it, the
upstream C++ server does not decode percent-encoded UTF-8 query parameters.

## Capability boundary

The documented HTTP protocol has no authoritative trading-calendar or
historical index-constituent / weight endpoint. Those methods explicitly raise
\`NotImplementedError\`. ETF bars can be exported, but the full-history gate
will remain UNKNOWN until calendar and historical index sources are connected.
No missing data is synthesized.

free-stockdb is a storage/query engine, not a public market-data mirror. A cloud
deployment must be populated from a trusted, licensed mirror using its updater
\`sync_url.txt\` / \`--source\` manifest. The public \`sync_url.txt\` contains
examples only and does not identify a live data mirror.

The upstream server has no built-in authentication or TLS. Do not expose it
directly to the public internet; place it behind an authenticated HTTPS reverse
proxy and network allowlist.
