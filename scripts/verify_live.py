"""Run one approved synthetic case through the real local HTTP runner."""

import argparse
import copy
import json
from datetime import date

from backend.app.engine.test_generator import generate_cases
from backend.app.engine.validator import validate_cases
from backend.app.runner.executor import execute_cases

SOURCE = "For overnight work, deduct one approved unpaid meal and apply per-shift overtime."


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True,
                        choices=["1.3.0", "1.3.0-b", "1.3.0-c", "1.4.0"])
    parser.add_argument("--case", choices=["overnight_with_break", "threshold_exact", "daytime_with_break"])
    args = parser.parse_args()
    with open("policies/sample_policies.json", encoding="utf-8") as stream:
        policies = {item["id"]: item for item in json.load(stream)["policies"]}
    cases = generate_cases("RQ-014", "AC-01")
    for case in cases:
        case["source_spans"] = [{"source_id": "RQ-014", "start": 0,
                                 "end": 18, "text": SOURCE[:18]}]
    issues = validate_cases(cases, requirements={"RQ-014": {}},
                            criteria={"AC-01": {"requirement_id": "RQ-014"}},
                            policies=policies, sources={"RQ-014": SOURCE},
                            on_date=date(2026, 11, 4))
    if issues:
        raise RuntimeError(f"plan validation failed: {issues}")
    case_name = {"1.3.0": "overnight_with_break", "1.3.0-b": "threshold_exact",
                 "1.3.0-c": "daytime_with_break", "1.4.0": "overnight_with_break"}[args.version]
    case = next(case for case in cases if case["id"].endswith(args.case or case_name))
    # This command-line probe simulates a stored human decision; the backend must
    # replace this callback with Member 1's authoritative persistence lookup.
    case.update(validation_state="VALID", approval_state="APPROVED")
    canonical = copy.deepcopy(case)
    def load_reviewed_case(test_id: str) -> dict | None:
        if test_id != canonical["id"]:
            return None
        return {"case": copy.deepcopy(canonical), "issues": copy.deepcopy(issues),
                "approval": {"test_id": test_id, "case_version": canonical["version"],
                             "decision": "APPROVED", "reviewer_id": "probe-reviewer",
                             "warnings_acknowledged": False}}
    results = execute_cases([case], selected_version=args.version, issues=issues,
                            load_reviewed_case=load_reviewed_case)
    print(json.dumps(results[0], indent=2))


if __name__ == "__main__":
    main()
