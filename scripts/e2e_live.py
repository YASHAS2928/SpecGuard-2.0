"""Run the full SpecGuard journey over real HTTP and print the result of every step.

Usage (backend and mock API already running, fictional data only):

    python -m scripts.e2e_live --backend http://127.0.0.1:18080 --mock http://127.0.0.1:19000 --samples .tmp/samples.json

Nothing is sent anywhere except the two loopback URLs you pass. Exits non-zero if any step fails.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

import httpx

TEXT = ("For an overnight shift, calculate overtime correctly after the employee has worked the "
        "configured number of paid hours, excluding the unpaid meal break.")
V1 = ["POL-OT-01@v1", "POL-MEAL-02@v1", "POL-DATE-03@v1"]
V2 = ["POL-OT-01@v2", "POL-MEAL-02@v1", "POL-DATE-03@v1"]
BA = {"actor": "asha.ba", "actor_role": "BUSINESS_ANALYST"}
QA = {"actor": "ravi.qa", "actor_role": "QA_ENGINEER"}


class Journey:
    def __init__(self, backend: str, mock: str) -> None:
        self.api = httpx.Client(base_url=backend, timeout=30, trust_env=False)
        self.mock = httpx.Client(base_url=mock, timeout=10, trust_env=False)
        self.samples: dict[str, Any] = {}
        self.failures = 0

    def call(self, method: str, path: str, expect: int, sample: str | None = None, **kwargs: Any) -> Any:
        response = self.api.request(method, path, **kwargs)
        if response.status_code != expect:
            raise SystemExit(f"{method} {path} -> {response.status_code} (expected {expect}): {response.text[:400]}")
        body = response.json()
        if sample:
            self.samples[sample] = body
        return body

    def step(self, name: str, ok: bool, detail: str) -> None:
        self.failures += 0 if ok else 1
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    def use_mock(self, version: str) -> None:
        response = self.mock.post("/admin/version", json={"version": version})
        response.raise_for_status()

    def approve(self, version_id: str, sample: str | None = None) -> dict[str, Any]:
        spec = self.call("POST", f"/requirement-versions/{version_id}/analyze", 200, json=BA)["spec"]
        for amb in spec["ambiguities"]:
            self.call("POST", f"/ambiguities/{amb['id']}/resolve", 200, json={**BA, "option_index": 0})
        return self.call("POST", f"/specs/{spec['id']}/approve", 200, sample, json=BA)

    def approve_engine_tests(self, spec_id: str) -> None:
        tests = self.call("GET", f"/specs/{spec_id}/tests", 200, params={"origin": "ENGINE", "status": "DRAFT"})
        self.call("POST", "/tests/review", 200, "review", json={**QA, "decision": "APPROVE", "test_ids": [t["id"] for t in tests]})

    def run(self, spec_id: str, sample: str | None = None, **extra: Any) -> dict[str, Any]:
        return self.call("POST", "/runs", 201, sample, json={**QA, "spec_id": spec_id, "test_ids": None, "trigger": "MANUAL", **extra})

    def execute(self) -> int:
        print("health:", self.call("GET", "/health", 200)["status"], "| version:", self.call("GET", "/version", 200)["version"])
        self.use_mock("1.3.0")
        requirement = self.call("POST", "/requirements", 201, "requirement", json={
            "code": f"RQ-{uuid.uuid4().int % 900000 + 100000}", "title": "Overnight overtime", "text": TEXT,
            "policy_ids": V1, **BA})
        spec1 = self.approve(requirement["versions"][0]["id"], "spec")
        self.step("1 approve spec v1", spec1["status"] == "APPROVED" and all(r["grounded"] for r in spec1["rules"]),
                  f"{len(spec1['rules'])} rules grounded, status {spec1['status']}")

        designed = self.call("POST", f"/specs/{spec1['id']}/design-tests", 200, "design", json={**QA, "include_ai_edge_cases": True})
        self.step("2 design tests", len(designed["tests"]) == 17 and designed["blocked_count"] == 2,
                  f"{len(designed['tests'])} tests, {designed['blocked_count']} blocked, AI {designed['ai_edge_cases']}")
        self.approve_engine_tests(spec1["id"])

        results: dict[str, list[str]] = {}
        for version in ("1.3.0", "1.3.0-b", "1.3.0-c", "1.4.0"):
            self.use_mock(version)
            body = self.run(spec1["id"], "run_seeded" if version == "1.3.0" else None)
            results[version] = sorted(r["tc_code"] for r in body["results"] if r["status"] == "FAIL")
            self.step(f"3 run on mock {version}", body["sut_version"] == version and body["totals"]["errors"] == 0,
                      f"{body['totals']['passed']} passed, {body['totals']['failed']} failed ({', '.join(results[version]) or 'none'})")
        self.step("3b seeded defects detected, 1.4.0 green", bool(results["1.3.0"] and results["1.3.0-b"] and results["1.3.0-c"])
                  and not results["1.4.0"], "each seeded version fails; the fixed version passes")
        defects = self.call("GET", "/defects", 200, "defects", params={"spec_id": spec1["id"]})
        self.step("4 no defect stays OPEN after the fix", bool(defects) and {d["status"] for d in defects} <= {"FIXED", "VERIFIED"},
                  ", ".join(f"{d['cluster_key']}={d['status']}" for d in defects))
        self.run(spec1["id"])
        verified = self.call("GET", "/defects", 200, params={"spec_id": spec1["id"]})
        self.step("4b defects VERIFIED after a second green run", {d["status"] for d in verified} == {"VERIFIED"}, "")

        version = self.call("POST", f"/requirements/{requirement['id']}/versions", 201, json={
            "text": TEXT, "policy_ids": V2, "change_note": "POL-OT-01 v2 lowers the threshold to 450.", **BA})
        spec2 = self.approve(version["id"])
        impact = self.call("POST", f"/specs/{spec2['id']}/impact", 201, "impact", json={**QA, "from_spec_id": spec1["id"]})
        self.step("5 change impact", impact["counts"]["STALE_EXPECTED"] > 0 and impact["rerun_test_ids"],
                  f"counts {impact['counts']}, rerun {len(impact['rerun_test_ids'])} tests")
        self.approve_engine_tests(spec2["id"])
        drift = self.run(spec2["id"], "run_drift", trigger="IMPACT_RERUN")
        drift_codes = sorted(r["tc_code"] for r in drift["results"] if r["status"] == "FAIL")
        self.step("6 drift on 1.4.0 (still threshold 480)", bool(drift_codes) and drift["totals"]["errors"] == 0,
                  f"{drift['totals']['failed']} failed ({', '.join(drift_codes)})")
        self.use_mock("1.5.0")
        final = self.run(spec2["id"], "run_final")
        self.step("7 green on 1.5.0 (threshold 450)", final["totals"]["failed"] == 0 and final["totals"]["errors"] == 0,
                  f"{final['totals']['passed']}/{final['totals']['total']} passed")

        self.call("GET", "/metrics/overview", 200, "metrics")
        self.call("GET", "/audit", 200, "audit", params={"entity_id": impact["id"]})
        self.call("GET", f"/specs/{spec2['id']}/tests", 200, "tests", params={"status": "APPROVED"})
        self.call("GET", f"/runs/{final['id']}", 200)
        print("failures:", self.failures)
        return self.failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", default="http://127.0.0.1:8000")
    parser.add_argument("--mock", default="http://127.0.0.1:9000")
    parser.add_argument("--samples", help="write the real responses used as documentation examples to this JSON file")
    args = parser.parse_args()
    journey = Journey(args.backend, args.mock)
    try:
        failures = journey.execute()
    finally:
        journey.mock.delete("/admin/version")
    if args.samples:
        path = Path(args.samples)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(journey.samples, indent=2), encoding="utf-8")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
