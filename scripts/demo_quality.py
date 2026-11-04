"""Offline demonstration of the exact case against seeded and corrected code."""

import json
import os
from datetime import date
from unittest.mock import patch

from fastapi import Response
import httpx

from backend.app.engine.defect_clustering import cluster_failures
from backend.app.engine.test_generator import generate_cases
from backend.app.engine.validator import validate_cases
from backend.app.runner.executor import execute_cases
from mock_api.main import PayRequest, calculate_pay

SOURCE = "For overnight work, deduct one approved unpaid meal and apply per-shift overtime."


def transport_for(version: str) -> httpx.Client:
    def handle(request: httpx.Request) -> httpx.Response:
        with patch.dict(os.environ, {"MOCK_VERSION": version}):
            response = Response()
            body = calculate_pay(PayRequest.model_validate_json(request.content), response)
        return httpx.Response(200, headers=dict(response.headers), json=body)
    return httpx.Client(transport=httpx.MockTransport(handle))


def main() -> None:
    cases = generate_cases("RQ-014", "AC-01")
    for case in cases:
        case["source_spans"] = [{"source_id": "RQ-014", "start": 0,
                                 "end": 18, "text": SOURCE[:18]}]
    with open("policies/sample_policies.json", encoding="utf-8") as stream:
        policies = {item["id"]: item for item in json.load(stream)["policies"]}
    issues = validate_cases(cases, requirements={"RQ-014": {}},
                            criteria={"AC-01": {"requirement_id": "RQ-014"}},
                            policies=policies, sources={"RQ-014": SOURCE},
                            on_date=date(2026, 11, 4))
    if issues:
        raise RuntimeError(f"demo cases failed validation: {issues}")
    case = next(case for case in cases if case["partition"] == "overnight")
    # Simulated human decision for this offline demo; real integration must load a persisted approval.
    case.update(validation_state="VALID", approval_state="APPROVED")
    results = []
    for version in ("1.3.0", "1.4.0"):
        with transport_for(version) as client:
            results.extend(execute_cases([case], selected_version=version,
                                         issues=issues, client=client))
    print(json.dumps({"cases_generated": len(cases), "validation_issues": issues,
                      "results": results, "defect_clusters": cluster_failures(results, [case])},
                     indent=2))


if __name__ == "__main__":
    main()
