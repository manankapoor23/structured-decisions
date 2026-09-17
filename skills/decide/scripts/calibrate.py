#!/usr/bin/env python3
"""Measure how well reported confidence matches observed outcomes.

Reads JSONL rows of {"confidence": 0.0-1.0, "correct": true|false} and prints
one JSON object per populated bin, then a summary object.

  mean_confidence vs empirical_accuracy   per-bin gap; the raw calibration curve
  ece                                     expected calibration error, the
                                          count-weighted mean of those gaps
  brier                                   mean squared error of the confidence
                                          values themselves

Lower ece and brier are better. An ece near 0 means confidence tracks accuracy
in aggregate; it does not mean any individual answer is right.
"""
import argparse
import json


def load(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for number, line in enumerate(f, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            confidence = float(row["confidence"])
            if not 0 <= confidence <= 1:
                raise SystemExit(f"line {number}: confidence {confidence} is outside 0 to 1")
            rows.append((confidence, bool(row["correct"])))
    return rows


def binned(rows, bins):
    for b in range(bins):
        low, high = b / bins, (b + 1) / bins
        group = [(c, ok) for c, ok in rows if low <= c < high or (b == bins - 1 and c == high)]
        if group:
            yield {
                "lower": round(low, 4),
                "upper": round(high, 4),
                "count": len(group),
                "mean_confidence": round(sum(c for c, _ in group) / len(group), 4),
                "empirical_accuracy": round(sum(ok for _, ok in group) / len(group), 4),
            }


def summarize(rows, buckets):
    total = len(rows)
    ece = sum(b["count"] / total * abs(b["empirical_accuracy"] - b["mean_confidence"]) for b in buckets)
    brier = sum((c - (1.0 if ok else 0.0)) ** 2 for c, ok in rows) / total
    return {
        "summary": {
            "count": total,
            "mean_confidence": round(sum(c for c, _ in rows) / total, 4),
            "accuracy": round(sum(ok for _, ok in rows) / total, 4),
            "ece": round(ece, 4),
            "brier": round(brier, 4),
            "bins_populated": len(buckets),
        }
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", help="path to a JSONL file of predictions")
    parser.add_argument("--bins", type=int, default=10, help="number of confidence bins (default 10)")
    args = parser.parse_args()

    rows = load(args.input)
    if not rows:
        raise SystemExit("No rows")

    buckets = list(binned(rows, max(1, args.bins)))
    for bucket in buckets:
        print(json.dumps(bucket))
    print(json.dumps(summarize(rows, buckets)))


if __name__ == "__main__":
    main()
