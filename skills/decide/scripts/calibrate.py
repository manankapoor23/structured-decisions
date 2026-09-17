#!/usr/bin/env python3
"""Compute empirical confidence calibration bins from JSONL predictions."""
import argparse, json

def main():
    p = argparse.ArgumentParser(); p.add_argument("input"); p.add_argument("--bins", type=int, default=10); args = p.parse_args()
    rows=[]
    with open(args.input, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r=json.loads(line); rows.append((float(r["confidence"]), bool(r["correct"])))
    if not rows: raise SystemExit("No rows")
    bins=max(1,args.bins)
    for b in range(bins):
        lo,hi=b/bins,(b+1)/bins
        group=[(c,ok) for c,ok in rows if (lo<=c<hi) or (b==bins-1 and c==hi)]
        if group:
            print(json.dumps({"lower":lo,"upper":hi,"count":len(group),"mean_confidence":round(sum(c for c,_ in group)/len(group),4),"empirical_accuracy":round(sum(ok for _,ok in group)/len(group),4)}))
if __name__ == "__main__": main()
