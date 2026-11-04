"""Check the configured AI provider without surprises.

    python -m scripts.check_ai_provider            # prints provider, model, configured; NO network call
    python -m scripts.check_ai_provider --live     # ALSO runs one RQ-014 extraction with the real provider

The default run never contacts a provider. ``--live`` sends the synthetic RQ-014 requirement and the
fictional policy texts (never anything else) to the configured provider, so use it only when your
company policy allows that provider. API keys are never printed: only whether they are set.
Exit codes: 0 ok, 1 the live call failed, 2 the provider is not configured.
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))  # makes ``app`` importable

from app.ai.adapter import get_ai_provider  # noqa: E402
from app.core.config import Settings, get_settings
from app.core.contracts import PolicyResponse
from app.core.errors import ApiError
from app.database.seed import FICTIONAL_POLICIES
from app.engine.interface import check_spec

REQUIREMENT_TEXT = (
    "For an overnight shift, calculate overtime correctly after the employee has worked the configured "
    "number of paid hours, excluding the unpaid meal break."
)
V1_REFS = ("POL-OT-01@v1", "POL-MEAL-02@v1", "POL-DATE-03@v1")


def demo_policies() -> list[PolicyResponse]:
    return [
        PolicyResponse(
            id=uuid.uuid4(), policy_code=s.policy_code, version=s.version, ref=f"{s.policy_code}@v{s.version}",
            title=s.title, rule_text=s.rule_text, effective_from=s.effective_from, effective_to=s.effective_to)
        for s in FICTIONAL_POLICIES if f"{s.policy_code}@v{s.version}" in V1_REFS
    ]


def describe(settings: Settings) -> list[str]:
    issues = settings.ai_configuration_issues()
    lines = [f"provider:   {settings.ai_provider}", f"model:      {settings.active_ai_model or '<not set>'}",
             f"configured: {'yes' if not issues else 'no'}"]
    lines += [f"issue:      {issue}" for issue in issues]
    return lines


def run_live(settings: Settings) -> tuple[int, list[str]]:
    provider = get_ai_provider(settings)
    policies = demo_policies()
    started = time.perf_counter()
    try:
        result = provider.extract_requirement(requirement_text=REQUIREMENT_TEXT, policies=policies)
    except ApiError as exc:
        return 1, [f"live call failed: {exc.code.value}: {exc.message}"]
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    issues = check_spec(result.data, REQUIREMENT_TEXT, policies)
    ungrounded = {(i.detail or {}).get("rule_key") for i in issues if i.code.value == "V02_UNGROUNDED_SPAN"}
    total = len(result.data.rules)
    return 0, [
        "schema-valid: yes",  # an invalid answer raises instead of returning
        f"first-try valid: {'yes' if result.valid_first_try else 'no'}",
        f"retries:    {result.retries}",
        f"latency:    {elapsed_ms} ms",
        f"rules:      {total}, ambiguities: {len(result.data.ambiguities)}",
        f"grounded rules: {total - len(ungrounded)} of {total}",
        f"tokens:     in={result.tokens_in} out={result.tokens_out}",
    ]


def main(argv: Sequence[str] | None = None, settings: Settings | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help="run ONE real extraction (makes a network call for real providers)")
    args = parser.parse_args(argv)
    current = settings or get_settings()
    print("\n".join(describe(current)))
    if not args.live:
        print("(no network call made; pass --live to test the provider)")
        return 0 if current.is_ai_configured else 2
    if not current.is_ai_configured:
        print("cannot run --live: the provider is not configured")
        return 2
    code, lines = run_live(current)
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main())
