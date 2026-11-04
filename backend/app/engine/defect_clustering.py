"""Cluster observed FAIL results only; no inferred root cause."""

import hashlib


def cluster_failures(results: list[dict], cases: list[dict]) -> list[dict]:
    by_id = {case["id"]: case for case in cases}
    groups: dict[tuple[str, str, str], list[str]] = {}
    for result in results:
        if result.get("status") != "FAIL" or result.get("test_id") not in by_id:
            continue
        case = by_id[result["test_id"]]
        key = case["rule_key"], case["partition"], case["technique"]
        groups.setdefault(key, []).append(result["test_id"])
    output = []
    for (rule, partition, technique), test_ids in sorted(groups.items()):
        digest = hashlib.sha256(repr((rule, partition, technique)).encode()).hexdigest()[:12]
        output.append({"cluster_id": f"DC-{digest}", "rule_key": rule,
                       "partition": partition, "technique": technique,
                       "failure_count": len(test_ids), "test_ids": sorted(test_ids)})
    return output
