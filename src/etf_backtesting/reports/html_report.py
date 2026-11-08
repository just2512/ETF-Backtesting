"""Self-contained interactive HTML renderer for strategy comparison artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _safe_json(value: Any) -> str:
    # Prevent embedded data from terminating the script element.
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace(
        "<", "\\u003c"
    ).replace(">", "\\u003e").replace("&", "\\u0026")


def render_comparison_html(
    comparison_dir: Path,
    output_path: Path | None = None,
) -> Path:
    """Render comparison.json and its per-run reports into one offline HTML file."""
    comparison_dir = comparison_dir.resolve()
    index_path = comparison_dir / "comparison.json"
    if not index_path.is_file():
        raise FileNotFoundError(f"comparison manifest not found: {index_path}")

    manifest = json.loads(index_path.read_text(encoding="utf-8"))
    runs: list[dict[str, Any]] = []
    for item in manifest.get("runs", []):
        relative = Path(item["artifacts"]["summary"])
        report_path = (comparison_dir / relative).resolve()
        if comparison_dir not in report_path.parents:
            raise ValueError(f"report path escapes comparison directory: {relative}")
        if not report_path.is_file():
            raise FileNotFoundError(f"run report not found: {report_path}")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        runs.append({
            "strategy": item["strategy"],
            "symbol_scope": item["symbol_scope"],
            "run_id": item["run_id"],
            "gates": item["gates"],
            "summary": item["summary"],
            "report": report,
        })

    payload = {
        "comparison_id": manifest.get("comparison_id"),
        "data_snapshot_sha256": manifest.get("data_snapshot_sha256"),
        "run_config_sha256": manifest.get("run_config_sha256"),
        "run_config": manifest.get("run_config", {}),
        "trading_days": manifest.get("trading_days", []),
        "formal_comparison_allowed": manifest.get("formal_comparison_allowed", False),
        "runs": runs,
    }
    html = _HTML.replace("__REPORT_DATA__", _safe_json(payload))
    destination = output_path or (comparison_dir / "comparison.html")
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.write_text(html, encoding="utf-8", newline="")
    temporary.replace(destination)
    return destination


_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ETF 策略回测对比报告</title>
<style>
:root{color-scheme:light;--bg:#f4f6f8;--panel:#fff;--ink:#17212b;--muted:#657382;--line:#dce2e8;--accent:#245b8f;--warn:#8b5a13;--bad:#a12b2b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.55 "Segoe UI","Microsoft YaHei",sans-serif}
main{max-width:1500px;margin:auto;padding:24px}.top{display:flex;gap:20px;justify-content:space-between;align-items:flex-start;flex-wrap:wrap}
h1{font-size:25px;margin:0 0 5px}.sub,.muted{color:var(--muted)}.status{padding:7px 11px;border-radius:7px;background:#fff1d8;color:var(--warn);font-weight:600}
.toolbar,.panel,.kpi{background:var(--panel);border:1px solid var(--line);border-radius:11px}
.toolbar{padding:16px;margin:20px 0;display:flex;gap:18px;align-items:end;flex-wrap:wrap}
.field{display:flex;flex-direction:column;gap:5px;min-width:170px}label{font-weight:600;color:#3d4a56}
select{padding:9px 10px;border:1px solid #c7d0d9;border-radius:7px;background:white;color:var(--ink);min-width:160px}
.checks{display:flex;gap:12px;flex-wrap:wrap;padding:8px 0}.checks label{font-weight:500}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:14px 0}
.kpi{padding:14px 16px}.kpi .name{color:var(--muted);font-size:12px}.kpi .value{font-size:22px;font-weight:700;margin-top:3px;overflow-wrap:anywhere}
.charts{display:grid;grid-template-columns:1fr 1fr;gap:14px}.panel{padding:16px;margin-bottom:14px;min-width:0}
.panel h2{font-size:16px;margin:0 0 12px}.chart{width:100%;height:300px;display:block}.legend{display:flex;gap:14px;flex-wrap:wrap;color:var(--muted);font-size:12px}.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:right;padding:9px 8px;border-bottom:1px solid var(--line);white-space:nowrap}th:first-child,td:first-child{text-align:left}th{color:var(--muted);font-weight:600;position:sticky;top:0;background:white}
.table-wrap{overflow:auto;max-height:440px}.gate{font-weight:700}.pass{color:#176b43}.unknown,.missing{color:var(--warn)}.reject{color:var(--bad)}
details{margin-top:10px}summary{cursor:pointer;font-weight:600}.meta{display:grid;grid-template-columns:180px 1fr;gap:6px 14px;overflow-wrap:anywhere}.meta div:nth-child(odd){color:var(--muted)}
.empty{padding:28px;text-align:center;color:var(--muted);background:#fff;border:1px dashed var(--line);border-radius:10px}
footer{color:var(--muted);font-size:12px;margin:20px 0}
@media(max-width:900px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.charts{grid-template-columns:1fr}}
@media(max-width:520px){main{padding:12px}.grid{grid-template-columns:1fr 1fr}.kpi .value{font-size:18px}.toolbar{gap:12px}.field{min-width:100%}}
</style>
</head>
<body>
<main>
<header class="top">
 <div><h1>ETF 策略回测对比报告</h1><div class="sub" id="subtitle">本地离线报告 · 数据来自实际回测产物</div></div>
 <div class="status" id="formal-status">正式回测门禁状态</div>
</header>
<section class="toolbar">
 <div class="field"><label for="scope">ETF / 组合范围</label><select id="scope"></select></div>
 <div class="field"><label>策略对比</label><div class="checks" id="strategy-checks"></div></div>
 <div class="field"><label for="metric">主图指标</label><select id="metric"><option value="nav">单位净值（剔除外部投入）</option><option value="total_value">账户总资产</option><option value="holdings_value">持仓市值</option><option value="cash">现金余额</option></select></div>
</section>
<div id="no-data" class="empty" hidden>当前筛选条件没有可展示的真实回测结果。请先完成数据导入和回测运行。</div>
<section class="grid" id="kpis"></section>
<section class="charts">
 <article class="panel"><h2 id="main-chart-title">净值曲线对比</h2><canvas class="chart" id="main-chart"></canvas><div class="legend" id="main-legend"></div></article>
 <article class="panel"><h2>回撤曲线</h2><canvas class="chart" id="dd-chart"></canvas><div class="legend" id="dd-legend"></div></article>
 <article class="panel"><h2>现金与持仓市值</h2><canvas class="chart" id="asset-chart"></canvas><div class="legend" id="asset-legend"></div></article>
 <article class="panel"><h2>交易执行状态</h2><div class="table-wrap"><table><thead><tr><th>策略 / 范围</th><th>成交</th><th>部分成交</th><th>拒单</th><th>未成交</th><th>费用</th><th>换手</th></tr></thead><tbody id="execution-table"></tbody></table></div></article>
</section>
<section class="panel"><h2>策略结果对照</h2><div class="table-wrap"><table><thead><tr><th>策略 / 范围</th><th>正式门禁</th><th>区间</th><th>期末资产</th><th>单位净值</th><th>时间加权收益</th><th>最大回撤</th><th>累计投入</th><th>期末现金</th></tr></thead><tbody id="summary-table"></tbody></table></div></section>
<section class="panel"><h2>运行与数据来源</h2><div class="meta" id="metadata"></div></section>
<section class="panel"><h2>当前选择的交易明细</h2><div class="table-wrap"><table><thead><tr><th>执行日期</th><th>证券</th><th>方向</th><th>状态</th><th>数量</th><th>成交价</th><th>成交额</th><th>费用</th><th>原因</th></tr></thead><tbody id="trades-table"></tbody></table></div></section>
<footer>说明：本报告只展示输入的回测产物，不补造缺失行情。正式门禁未通过时，图表仅供研究分析，不能解释为可用于实盘决策的正式回测结果。所有金额与收益均沿用回测报告原始口径。</footer>
</main>
<script id="report-data" type="application/json">__REPORT_DATA__</script>
<script>
"use strict";
const DATA=JSON.parse(document.getElementById("report-data").textContent);
const COLORS=["#27618f","#b05a38","#39836c","#8063a6","#b28a28","#3f7c8b","#9a526f"];
const names={A:"A 固定定投",B:"B 布林积累",C:"C 布林买卖",D:"D 公共资金池"};
const fmt=(v,unit="")=>{if(v===null||v===undefined||v==="")return "—";const n=Number(v);return Number.isFinite(n)?n.toLocaleString("zh-CN",{maximumFractionDigits:4})+unit:String(v)};
const pct=v=>v===null||v===undefined?"—":fmt(Number(v)*100,"%");
const status=(g)=>g?.formal_result_allowed?"PASS":"BLOCKED";
const scope=document.getElementById("scope"),checks=document.getElementById("strategy-checks");
const scopes=[...new Set(DATA.runs.map(r=>r.symbol_scope))];
scope.innerHTML='<option value="ALL">全部 ETF / 组合</option>'+scopes.map(s=>'<option value="'+s+'">'+(s==="SHARED_POOL"?"公共资金池":s)+'</option>').join("");
["A","B","C","D"].forEach((s,i)=>{const label=document.createElement("label");label.innerHTML='<input type="checkbox" value="'+s+'" '+(s!=="D"?"checked":"")+'> '+names[s];checks.appendChild(label)});
function selected(){const s=scope.value,strategies=[...checks.querySelectorAll("input:checked")].map(x=>x.value);return DATA.runs.filter(r=>(s==="ALL"||r.symbol_scope===s)&&strategies.includes(r.strategy))}
function canvasSetup(canvas){const ratio=window.devicePixelRatio||1,w=canvas.clientWidth,h=canvas.clientHeight;canvas.width=w*ratio;canvas.height=h*ratio;const c=canvas.getContext("2d");c.scale(ratio,ratio);return {c,w,h}}
function lineChart(id,series,key,legendId,percent=false){const canvas=document.getElementById(id),{c,w,h}=canvasSetup(canvas),L=54,R=14,T=15,B=34,pw=w-L-R,ph=h-T-B;
 c.clearRect(0,0,w,h);if(!series.length){c.fillStyle="#657382";c.fillText("无可展示数据",L,T+30);return}
 const vals=series.flatMap(s=>s.points.map(p=>Number(p[key])).filter(Number.isFinite));if(!vals.length)return;
 let min=Math.min(...vals),max=Math.max(...vals);if(min===max){min-=.02;max+=.02}if(percent&&max>0)max=Math.max(0,max);
 const y=v=>T+(max-v)/(max-min)*ph,x=i=>L+(series[0].points.length<=1?0:i/(series[0].points.length-1)*pw);
 c.font="11px sans-serif";c.strokeStyle="#e3e8ed";c.fillStyle="#657382";c.lineWidth=1;
 for(let i=0;i<=4;i++){const v=min+(max-min)*i/4,yy=y(v);c.beginPath();c.moveTo(L,yy);c.lineTo(w-R,yy);c.stroke();c.fillText(fmt(v,percent?"%":""),3,yy+4)}
 c.strokeStyle="#9aa7b3";c.beginPath();c.moveTo(L,T);c.lineTo(L,T+ph);c.lineTo(w-R,T+ph);c.stroke();
 series.forEach((s,idx)=>{const color=COLORS[idx%COLORS.length];c.strokeStyle=color;c.lineWidth=2;c.beginPath();let started=false;s.points.forEach((p,i)=>{const v=Number(p[key]);if(!Number.isFinite(v))return;const xx=x(i),yy=y(v);if(!started){c.moveTo(xx,yy);started=true}else c.lineTo(xx,yy)});c.stroke()});
 c.fillStyle="#657382";const dates=series[0].points;if(dates.length){c.fillText(dates[0].date||"",L,T+ph+22);const last=dates[dates.length-1];const label=last.date||"";c.fillText(label,Math.max(L,w-R-c.measureText(label).width),T+ph+22)}
 document.getElementById(legendId).innerHTML=series.map((s,i)=>'<span><i class="dot" style="background:'+COLORS[i%COLORS.length]+'"></i>'+s.label+'</span>').join("");
}
function update(){const runs=selected();document.getElementById("no-data").hidden=!!runs.length;
 ["kpis","summary-table","execution-table","trades-table","metadata"].forEach(id=>document.getElementById(id).innerHTML="");
 if(!runs.length){["main-chart","dd-chart","asset-chart"].forEach(id=>{const {c,w,h}=canvasSetup(document.getElementById(id));c.fillStyle="#657382";c.fillText("无可展示数据",20,40)});return}
 const primary=runs[0],s=primary.summary;
 const kpis=[["期末账户资产",fmt(s.final_account_value)],["时间加权收益",pct(s.time_weighted_return)],["最大回撤",pct(s.maximum_drawdown)],["累计外部投入",fmt(s.external_contributions)]];
 document.getElementById("kpis").innerHTML=kpis.map(k=>'<div class="kpi"><div class="name">'+k[0]+'</div><div class="value">'+k[1]+'</div></div>').join("");
 const metric=document.getElementById("metric").value;
 const points=r=>r.report.equity_curve||[];
 const series=runs.map(r=>({label:names[r.strategy]+" · "+r.symbol_scope,points:points(r)})).filter(s=>s.points.length);
 const title={nav:"单位净值曲线",total_value:"账户总资产曲线",holdings_value:"持仓市值曲线",cash:"现金余额曲线"};
 document.getElementById("main-chart-title").textContent=title[metric]+"对比";
 lineChart("main-chart",series,metric,"main-legend");
 lineChart("dd-chart",series,"drawdown","dd-legend");
 // Draw cash and holdings as separate series, retaining each selected run as a distinct line.
 const assets=[];series.forEach(s=>{assets.push({label:s.label+" · 现金",points:s.points.map(p=>({...p,total:Number(p.cash)}))});assets.push({label:s.label+" · 持仓",points:s.points.map(p=>({...p,total:Number(p.holdings_value)}))})});
 lineChart("asset-chart",assets,"total","asset-legend");
 document.getElementById("summary-table").innerHTML=runs.map(r=>{const x=r.summary,g=r.gates;return '<tr><td>'+names[r.strategy]+' · '+r.symbol_scope+'</td><td class="gate '+(g.formal_result_allowed?"pass":"unknown")+'">'+status(g)+'</td><td>'+x.first_date+' 至 '+x.last_date+'</td><td>'+fmt(x.final_account_value)+'</td><td>'+fmt(x.final_nav)+'</td><td>'+pct(x.time_weighted_return)+'</td><td>'+pct(x.maximum_drawdown)+'</td><td>'+fmt(x.external_contributions)+'</td><td>'+fmt(x.final_cash)+'</td></tr>'}).join("");
 document.getElementById("execution-table").innerHTML=runs.map(r=>{const x=r.summary;return '<tr><td>'+names[r.strategy]+' · '+r.symbol_scope+'</td><td>'+fmt(x.filled_orders)+'</td><td>'+fmt(x.partial_orders)+'</td><td>'+fmt(x.rejected_orders)+'</td><td>'+fmt(x.no_fill_orders)+'</td><td>'+fmt(x.fees)+'</td><td>'+fmt(x.turnover)+'</td></tr>'}).join("");
 const trades=primary.report.executions||[];document.getElementById("trades-table").innerHTML=trades.map(t=>'<tr><td>'+t.execution_date+'</td><td>'+t.symbol+'</td><td>'+t.side+'</td><td>'+t.status+'</td><td>'+fmt(t.quantity)+'</td><td>'+fmt(t.fill_price)+'</td><td>'+fmt(t.notional)+'</td><td>'+fmt(t.fee)+'</td><td>'+String(t.reason||"").replace(/[&<>"]/g,"")+'</td></tr>').join("");
 const meta=[["Comparison ID",DATA.comparison_id],["数据快照 SHA-256",DATA.data_snapshot_sha256],["运行配置 SHA-256",DATA.run_config_sha256],["正式比较门禁",DATA.formal_comparison_allowed?"PASS":"BLOCKED"],["当前主图运行 ID",primary.run_id],["策略参数",JSON.stringify(DATA.run_config)]];
 document.getElementById("metadata").innerHTML=meta.map(x=>'<div>'+x[0]+'</div><div>'+String(x[1]??"—").replace(/[&<>"]/g,"")+'</div>').join("");
 document.getElementById("formal-status").textContent=DATA.formal_comparison_allowed?"正式比较门禁：PASS":"正式比较门禁：BLOCKED（研究结果）";
}
scope.addEventListener("change",update);checks.addEventListener("change",update);document.getElementById("metric").addEventListener("change",update);window.addEventListener("resize",update);update();
</script>
</body></html>
"""
