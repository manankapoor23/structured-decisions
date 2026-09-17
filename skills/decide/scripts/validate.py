#!/usr/bin/env python3
"""Validate a typed decision without external dependencies."""
import json
import sys

ALLOWED_KINDS = {"observed", "inferred", "missing"}
REQUIRED = {"decision", "confidence", "needs_review", "abstained", "evidence", "reason", "missing_information"}

def validate(obj, allowed_decisions=None, require_evidence=True):
    errors = []
    if not isinstance(obj, dict): return ["decision must be an object"]
    missing = REQUIRED - obj.keys()
    if missing: errors.append(f"missing fields: {sorted(missing)}")
    extra = set(obj) - REQUIRED
    if extra: errors.append(f"unexpected fields: {sorted(extra)}")
    if not isinstance(obj.get("decision"), str) or not obj.get("decision"): errors.append("decision must be a non-empty string")
    if allowed_decisions is not None and obj.get("decision") not in allowed_decisions: errors.append(f"decision must be one of: {allowed_decisions}")
    c = obj.get("confidence")
    if isinstance(c, bool) or not isinstance(c, (int, float)) or not 0 <= c <= 1: errors.append("confidence must be a number between 0 and 1")
    if not isinstance(obj.get("needs_review"), bool): errors.append("needs_review must be boolean")
    if not isinstance(obj.get("abstained"), bool): errors.append("abstained must be boolean")
    if not isinstance(obj.get("reason"), str) or not obj.get("reason"): errors.append("reason must be a non-empty string")
    evidence = obj.get("evidence")
    if not isinstance(evidence, list): errors.append("evidence must be an array")
    else:
        if require_evidence and not evidence: errors.append("evidence must not be empty")
        for i, item in enumerate(evidence):
            if not isinstance(item, dict): errors.append(f"evidence[{i}] must be an object"); continue
            if set(item) != {"kind", "text"}: errors.append(f"evidence[{i}] must contain only kind and text")
            if item.get("kind") not in ALLOWED_KINDS: errors.append(f"evidence[{i}].kind must be one of {sorted(ALLOWED_KINDS)}")
            if not isinstance(item.get("text"), str) or not item.get("text"): errors.append(f"evidence[{i}].text must be a non-empty string")
    if not isinstance(obj.get("missing_information"), list) or not all(isinstance(x, str) for x in obj.get("missing_information", [])): errors.append("missing_information must be an array of strings")
    if obj.get("abstained") and not obj.get("needs_review"): errors.append("abstained decisions must require review")
    if obj.get("abstained") and not obj.get("missing_information"): errors.append("abstained decisions should identify missing information")
    return errors

def validate_batch(obj, allowed_by_id=None, require_evidence=True):
    """Validate {"judgments": {id: decision}}, one independent judgment per id."""
    if not isinstance(obj, dict): return ["batch must be an object"]
    extra = set(obj) - {"judgments"}
    if extra: return [f"unexpected fields: {sorted(extra)}"]
    judgments = obj.get("judgments")
    if not isinstance(judgments, dict): return ["judgments must be an object keyed by question id"]
    if not judgments: return ["judgments must not be empty"]
    errors = []
    for jid, judgment in judgments.items():
        allowed = (allowed_by_id or {}).get(jid)
        errors.extend(f"judgments.{jid}: {e}" for e in validate(judgment, allowed, require_evidence))
    return errors


def main():
    if len(sys.argv) != 2:
        print("usage: validate.py decision.json", file=sys.stderr); raise SystemExit(2)
    with open(sys.argv[1], encoding="utf-8") as f: obj = json.load(f)
    is_batch = isinstance(obj, dict) and "judgments" in obj
    errors = validate_batch(obj) if is_batch else validate(obj)
    if errors:
        print("INVALID")
        for e in errors: print(f"- {e}")
        raise SystemExit(1)
    print(f"VALID ({len(obj['judgments'])} judgments)" if is_batch else "VALID")

if __name__ == "__main__": main()
