#!/usr/bin/env python3
"""Measure how often reported confidence matched the outcome, and optionally
write a calibration artifact the gate can select thresholds from.

Input is JSONL, one prediction per line:

  {"confidence": 0.91, "correct": true}
  {"confidence": 0.91, "correct": true, "decision": "spam", "action": "auto_delete"}

`decision` and `action` are optional. When present, per-class and per-action
groups are measured alongside the global one, so a policy can hold a rare class
to a different threshold than a common one.

Printed per bin, and per group in the artifact:

  mean_confidence vs empirical_accuracy   the raw calibration curve
  ece                                     count-weighted mean gap between them
  brier                                   mean squared error of the confidences

What this does not establish:

  Observed accuracy is a count, not a probability. A group with 9 outcomes
  tells you very little, and nothing here computes a confidence interval or
  reports significance. Rows must come from the same model, prompt, and input
  distribution you intend to gate, or the numbers describe a different system.
  If you then select a threshold from these same rows, the accuracy you see in
  production will tend to be worse than the target, because the cutoff was
  fitted to the noise as well as the signal. Hold out a validation set.
"""
import argparse
import json
from collections import defaultdict


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
            rows.append((confidence, bool(row["correct"]), row.get("decision"), row.get("action")))
    return rows


def binned(rows, bins):
    for b in range(bins):
        low, high = b / bins, (b + 1) / bins
        group = [(c, ok) for c, ok, *_ in rows if low <= c < high or (b == bins - 1 and c == high)]
        if group:
            yield {
                "lower": round(low, 4),
                "upper": round(high, 4),
                "count": len(group),
                "mean_confidence": round(sum(c for c, _ in group) / len(group), 4),
                "empirical_accuracy": round(sum(ok for _, ok in group) / len(group), 4),
            }


def stats(rows, buckets):
    total = len(rows)
    ece = sum(b["count"] / total * abs(b["empirical_accuracy"] - b["mean_confidence"]) for b in buckets)
    brier = sum((c - (1.0 if ok else 0.0)) ** 2 for c, ok, *_ in rows) / total
    return {
        "count": total,
        "mean_confidence": round(sum(c for c, *_ in rows) / total, 4),
        "accuracy": round(sum(ok for _, ok, *_ in rows) / total, 4),
        "ece": round(ece, 4),
        "brier": round(brier, 4),
        "bins_populated": len(buckets),
    }


def group_rows(rows):
    """global, one group per class, one per action:class pair."""
    groups = {"global": list(rows)}
    by_class = defaultdict(list)
    by_pair = defaultdict(list)
    for row in rows:
        _, _, label, action = row
        if label:
            by_class[label].append(row)
            if action:
                by_pair[f"{action}:{label}"].append(row)
    groups.update(by_class)
    groups.update(by_pair)
    return groups


def build_artifact(rows, bins, min_samples):
    groups = {}
    for key, member_rows in sorted(group_rows(rows).items()):
        buckets = list(binned(member_rows, bins))
        groups[key] = {**stats(member_rows, buckets), "bins": buckets}
    return {
        "version": 1,
        "bins": bins,
        "min_samples": min_samples,
        "groups": groups,
        "caveat": (
            "Empirical counts from past outcomes, not probabilities. No confidence "
            "intervals are computed. A threshold selected from these same rows is "
            "optimistically biased; validate on held-out data."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", help="path to a JSONL file of predictions")
    parser.add_argument("--bins", type=int, default=10, help="number of confidence bins (default 10)")
    parser.add_argument("--artifact", metavar="PATH", help="write a calibration artifact for gate.py")
    parser.add_argument(
        "--min-samples", type=int, default=30,
        help="minimum labelled outcomes a group needs before a policy should trust it (default 30)",
    )
    args = parser.parse_args()

    rows = load(args.input)
    if not rows:
        raise SystemExit("No rows")
    bins = max(1, args.bins)

    buckets = list(binned(rows, bins))
    for bucket in buckets:
        print(json.dumps(bucket))
    print(json.dumps({"summary": stats(rows, buckets)}))

    if args.artifact:
        artifact = build_artifact(rows, bins, args.min_samples)
        with open(args.artifact, "w", encoding="utf-8") as f:
            json.dump(artifact, f, indent=2)
            f.write("\n")
        thin = [k for k, g in artifact["groups"].items()
                if k != "global" and g["count"] < args.min_samples]
        print(json.dumps({"artifact": args.artifact, "groups": len(artifact["groups"])}))
        if thin:
            print(json.dumps({"below_min_samples": sorted(thin), "min_samples": args.min_samples}))


if __name__ == "__main__":
    main()
