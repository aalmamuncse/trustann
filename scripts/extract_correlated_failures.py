#!/usr/bin/env python3
"""Validate and summarize an already-generated correlated_failures.csv.

Usage:
  python3 scripts/extract_correlated_failures.py path/to/correlated_failures.csv
"""
import argparse, csv, statistics
from pathlib import Path

REQUIRED={"experiment","query_id","trusted"}

def main():
    p=argparse.ArgumentParser(); p.add_argument("csv_path"); p.add_argument("--out",default="correlated_failures_summary.csv")
    a=p.parse_args(); rows=list(csv.DictReader(Path(a.csv_path).open(newline="")))
    if not rows: raise SystemExit("CSV is empty")
    missing=REQUIRED-set(rows[0])
    if missing: raise SystemExit(f"Missing required columns: {sorted(missing)}")
    groups={}
    for r in rows: groups.setdefault(r.get("pattern",r.get("scenario","unknown")),[]).append(r)
    out=[]
    for label,rr in groups.items():
        trusted=sum(int(r["trusted"]) for r in rr)/len(rr)
        domains=[float(r["min_diversity"]) for r in rr if r.get("min_diversity") not in (None,"")]
        out.append({"pattern":label,"queries":len(rr),"trusted_rate":trusted,"mean_min_diversity":statistics.mean(domains) if domains else ""})
    with open(a.out,"w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=out[0].keys()); w.writeheader(); w.writerows(out)
    print(f"Wrote {a.out}")
    for r in out: print(r)
if __name__=="__main__": main()
