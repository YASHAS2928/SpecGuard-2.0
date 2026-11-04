"""Seed the demo with the RQ-014 requirement (idempotent), through the real API.

    python -m scripts.seed_demo --backend http://127.0.0.1:8000

Creates requirement RQ-014 with the three v1 fictional policies so the UI is never empty. Nothing is
analysed or approved: the demo walks through that. Running it again changes nothing. Only the backend
URL you pass is contacted (loopback by default); the data is synthetic.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Sequence

import httpx

CODE = "RQ-014"
TITLE = "Overnight overtime with unpaid meal break"
TEXT = ("For an overnight shift, calculate overtime correctly after the employee has worked the configured "
        "number of paid hours, excluding the unpaid meal break.")
POLICY_IDS = ["POL-OT-01@v1", "POL-MEAL-02@v1", "POL-DATE-03@v1"]
ACTOR = {"actor": "asha.ba", "actor_role": "BUSINESS_ANALYST"}


def seed(client: httpx.Client) -> str:
    """Create RQ-014 unless it exists. Returns 'created' or 'already present'."""
    listing = client.get("/requirements")
    listing.raise_for_status()
    if any(item["code"] == CODE for item in listing.json()):
        return "already present"
    response = client.post("/requirements", json={
        "code": CODE, "title": TITLE, "text": TEXT, "policy_ids": POLICY_IDS, **ACTOR})
    if response.status_code == 409:  # created by a concurrent seed: same outcome
        return "already present"
    response.raise_for_status()
    return "created"


def wait_until_ready(client: httpx.Client, seconds: float = 30.0) -> None:
    deadline = time.monotonic() + seconds
    while True:
        try:
            if client.get("/health").status_code in (200, 503):
                return
        except httpx.HTTPError:
            pass
        if time.monotonic() > deadline:
            raise SystemExit("The backend did not become reachable in time.")
        time.sleep(0.5)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--backend", default="http://127.0.0.1:8000")
    args = parser.parse_args(argv)
    with httpx.Client(base_url=args.backend, timeout=15, trust_env=False) as client:
        wait_until_ready(client)
        print(f"{CODE}: {seed(client)} (policies {', '.join(POLICY_IDS)}; nothing analysed or approved)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
