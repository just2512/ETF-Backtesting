# 交互式 HTML 回测报告

每次调用 `write_comparison_report(comparison, output_dir)`，项目会自动在比较产物目录生成：

```text
comparison.html
comparison.json
comparison.csv
runs/
  510300/
    A/report.json
    A/equity_curve.csv
    A/executions.csv
    A/ledger_events.csv
  ...
```

HTML 是**单文件离线报告**：图表、筛选逻辑和各策略曲线数据都嵌入文件，不依赖 CDN、在线字体或第三方图表服务。将 `comparison.html` 复制到任意目录，使用 Edge/Chrome 打开即可。

## 页面交互

- ETF / 组合范围：选择单只 ETF、全部 ETF 或公共资金池。
- 策略对比：勾选 A 固定定投、B 布林积累、C 布林买卖、D 公共资金池；切换后曲线和对照表同步更新。
- 主图指标：切换单位净值、账户总资产、持仓市值和现金余额。
- 图表：单位净值/账户曲线、最大回撤、现金与持仓市值。
- 对照表：区间、期末资产、单位净值、时间加权收益、最大回撤、累计投入和期末现金。
- 交易明细：显示当前选择的首个策略运行的执行日期、证券、方向、状态、数量、价格、成交额、费用和原因。
- 运行元数据：显示数据快照 SHA-256、配置 SHA-256、比较 ID 和正式回测门禁。

## 生成命令

正常回测比较写盘时会自动生成 HTML。如果已有 JSON/CSV 产物，需要重新生成或修复 HTML：

```powershell
python scripts/render_comparison_html.py --comparison-dir reports/backtests/latest
```

也可以指定输出路径：

```powershell
python scripts/render_comparison_html.py --comparison-dir reports/backtests/latest --output reports/backtests/latest/ETF-Backtest-Report.html
```

## 数据与解释边界

- HTML 直接读取每个运行的 `report.json`，不会重新计算收益，也不会补齐行情。
- 单位净值使用回测引擎已经剥离外部投入的序列；回撤使用同一单位净值口径。
- 正式门禁未通过时，页面会标注 BLOCKED；曲线仅用于研究机制检查，不应被称为正式回测结果。
- 如果没有真实运行产物，渲染器会报缺少 manifest/report，不会输出演示数据或伪造图表。
- HTML 内含完整运行曲线和交易明细，可能较大；它适合本地查看和归档，不应上传含个人资金信息的公开站点。
