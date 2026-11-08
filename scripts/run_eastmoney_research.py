# ruff: noqa: E701, E702
"""Eastmoney full-history fetch and research-only A/B/C/D backtest."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import time
from datetime import date,datetime,timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from etf_backtesting.contracts import PriceBar
from etf_backtesting.engine.execution import TradingCostModel
from etf_backtesting.strategies.comparison import StrategyComparisonRunner
from etf_backtesting.reports.strategy_report import build_comparison_report,write_comparison_report
SYMBOLS=("510300","510880","513020","159928","159611")
LISTING={"510300":"2012-05-28","510880":"2007-01-18","513020":"2022-02-08","159928":"2013-09-16","159611":"2022-01-07"}
SECID={s:("1." if s.startswith(("5","6")) else "0.")+s for s in SYMBOLS}
URL="https://push2his.eastmoney.com/api/qt/stock/kline/get"
def fetch(symbol,start,end,attempts,delay):
 p={"secid":SECID[symbol],"ut":"fa5fd1943c7b386f172d6893dbfba10b","fields1":"f1,f2,f3,f4,f5,f6","fields2":"f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61","klt":"101","fqt":"0","beg":start.replace("-",""),"end":end.replace("-",""),"lmt":"100000"}
 req=Request(URL+"?"+urlencode(p),headers={"User-Agent":"Mozilla/5.0 ETF-Backtesting/1.0","Referer":"https://quote.eastmoney.com/","Accept":"application/json"})
 errors=[]
 for n in range(1,attempts+1):
  try:
   with urlopen(req,timeout=45) as response:
    if response.status!=200: raise OSError("HTTP "+str(response.status))
    payload=json.loads(response.read().decode("utf-8"))
   data=payload.get("data")
   if not isinstance(data,dict) or not isinstance(data.get("klines"),list): raise ValueError("response missing data.klines: "+repr(payload)[:500])
   rows=[]
   for line in data["klines"]:
    x=line.split(",")
    if len(x)<11: raise ValueError("malformed kline: "+line)
    rows.append(dict(trade_date=x[0],open=x[1],close=x[2],high=x[3],low=x[4],volume=x[5],amount=x[6],amplitude=x[7],change_pct=x[8],change=x[9],turnover=x[10]))
   if not rows: raise ValueError("zero rows returned for "+symbol)
   return rows
  except Exception as exc:
   errors.append("attempt "+str(n)+": "+type(exc).__name__+": "+str(exc))
   if n==attempts: raise RuntimeError(" | ".join(errors)) from exc
   time.sleep(delay*(2**(n-1)))
 raise RuntimeError("unreachable retry state")
def main():
 ap=argparse.ArgumentParser(); ap.add_argument("--start",default="20070118"); ap.add_argument("--end",default=date.today().strftime("%Y%m%d"))
 ap.add_argument("--output",default="reports/eastmoney/latest"); ap.add_argument("--initial-cash",type=Decimal,default=Decimal("10000"))
 ap.add_argument("--retry-attempts",type=int,default=4); ap.add_argument("--retry-delay-seconds",type=float,default=2); a=ap.parse_args()
 start=date.fromisoformat(a.start[:4]+"-"+a.start[4:6]+"-"+a.start[6:8]); end=date.fromisoformat(a.end[:4]+"-"+a.end[4:6]+"-"+a.end[6:8])
 if start>end or a.initial_cash<=0: raise ValueError("invalid date range or initial cash")
 out=Path(a.output); raw=out/"raw"; raw.mkdir(parents=True,exist_ok=True); audit=[]; bars={}
 for symbol in SYMBOLS:
  first=max(start,date.fromisoformat(LISTING[symbol]))
  try:
   rows=fetch(symbol,first.isoformat(),end.isoformat(),a.retry_attempts,a.retry_delay_seconds)
   rows=sorted((r for r in rows if first.isoformat()<=r["trade_date"]<=end.isoformat()),key=lambda r:r["trade_date"])
   if not rows: raise ValueError("no rows in requested interval")
   path=raw/(symbol+".csv"); fields=("symbol","trade_date","open","high","low","close","volume","amount","amplitude","change_pct","change","turnover","source","price_basis","fqt")
   with path.open("w",encoding="utf-8-sig",newline="") as h:
    w=csv.DictWriter(h,fieldnames=fields); w.writeheader()
    for r in rows: w.writerow({**r,"symbol":symbol,"source":"Eastmoney push2his","price_basis":"UNADJUSTED","fqt":0})
   digest=hashlib.sha256(path.read_bytes()).hexdigest(); first_seen=date.fromisoformat(rows[0]["trade_date"])
   audit.append({"symbol":symbol,"status":"PASS","rows":len(rows),"first_date":rows[0]["trade_date"],"last_date":rows[-1]["trade_date"],"expected_first_date":first.isoformat(),"first_date_status":"PASS" if first_seen==first else "UNKNOWN","sha256":digest,"file":"raw/"+path.name,"secid":SECID[symbol],"klt":101,"fqt":0})
   with path.open(encoding="utf-8-sig",newline="") as h:
    bars[symbol]=[PriceBar(symbol=symbol,trade_date=date.fromisoformat(r["trade_date"]),open=float(r["open"]),high=float(r["high"]),low=float(r["low"]),close=float(r["close"]),volume=float(r["volume"]),amount=float(r["amount"]),trade_status="NORMAL",source="Eastmoney push2his fqt=0") for r in csv.DictReader(h)]
   bars[symbol].sort(key=lambda x:x.trade_date)
   if len({x.trade_date for x in bars[symbol]})!=len(bars[symbol]): raise ValueError("duplicate dates")
  except Exception as exc: audit.append({"symbol":symbol,"status":"UNKNOWN","error_type":type(exc).__name__,"error":str(exc)})
 manifest={"schema_version":1,"generated_at":datetime.now(timezone.utc).isoformat(),"provider":"Eastmoney push2his","requested_start":start.isoformat(),"requested_end":end.isoformat(),"price_basis":"UNADJUSTED","fqt":0,"symbols":audit,"calendar_status":"UNKNOWN","limitations":["No official exchange calendar; absent bars cannot be classified as suspension or defect.","No official dividend-event coverage; cash distributions are omitted.","No historical bid/ask, limit-lock or suspension context; execution uses next-session OHLC open as a research proxy.","513020 premium/discount and cross-market valuation-time effects are not modelled."]}
 out.mkdir(parents=True,exist_ok=True); mp=out/"data_manifest.json"; mp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 if len(bars)!=len(SYMBOLS): print(json.dumps(manifest,ensure_ascii=False,indent=2)); return 2
 days=sorted({b.trade_date for series in bars.values() for b in series}); months={}
 for d in days: months.setdefault((d.year,d.month),d)
 dca_dates=set(months.values()); monthly=a.initial_cash/Decimal(len(dca_dates)); per=a.initial_cash/Decimal(5); reserve=a.initial_cash/Decimal(10)
 costs=TradingCostModel(Decimal("0.00015"),Decimal("0.00004"),Decimal("0"))
 config={"purpose":"RESEARCH_ONLY_NOT_FORMAL_INVESTMENT_BACKTEST","provider":"Eastmoney push2his","price_basis":"UNADJUSTED","fqt":0,"symbols":list(SYMBOLS),"initial_cash_per_run":str(a.initial_cash),"external_contributions":"NONE","A":{"schedule":"first observed session each month","monthly_budget":str(monthly)},"B_C_D":{"per_etf_cycle_budget":str(per)},"D":{"per_etf_max_market_value":str(per),"minimum_cash_reserve":str(reserve)},"fees":{"commission_rate":"0.00015","other_fee_rate":"0.00004","minimum_commission":"0","status":"RESEARCH_ASSUMPTION_NOT_BROKER_CONFIRMED"},"bollinger":{"period":20,"deviations":2.0,"ddof":0,"signal":"AFTER_CLOSE","execution":"NEXT_SESSION_OPEN"},"sell_mode":"S1","lot_size":100,"dividend_gate":"MISSING","execution_rules_gate":"UNKNOWN","research_only":True,"calendar":"UNION_OF_OBSERVED_ETF_DATES_NOT_OFFICIAL"}
 result=StrategyComparisonRunner(lot_size=100).run(bars,days,initial_cash=a.initial_cash,costs=costs,dca_budget_by_symbol={s:monthly for s in SYMBOLS},per_etf_cycle_budget={s:per for s in SYMBOLS},max_market_value_by_symbol={s:per for s in SYMBOLS},dca_dates=dca_dates,reserve_cash=reserve,sell_mode="S1",dividend_status="MISSING",execution_rules_status="UNKNOWN",research_only=True)
 digest=hashlib.sha256(mp.read_bytes()+b"".join((raw/(s+".csv")).read_bytes() for s in SYMBOLS)).hexdigest()
 report=build_comparison_report(result,data_snapshot_sha256=digest,run_config=config); report["formal_comparison_allowed"]=False; report["data_audit"]=manifest
 paths=write_comparison_report(report,out/"comparison")
 print(json.dumps({"data_manifest":str(mp),"comparison_html":paths["comparison_html"],"comparison_csv":paths["comparison_csv"],"data_snapshot_sha256":digest,"research_runs":len(report["runs"]),"formal_comparison_allowed":False,"symbols":audit},ensure_ascii=False,indent=2))
 return 0 if all(x["status"]=="PASS" and x["first_date_status"]=="PASS" for x in audit) else 3
if __name__=="__main__": raise SystemExit(main())
