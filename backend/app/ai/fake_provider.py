"""Deterministic fake provider used when no real model is configured."""

from __future__ import annotations

import copy
import json
import re
from typing import Any

from app.core.contracts import RQ014_EXTRACTION_EXAMPLE

from .adapter import Completion


def _source_span(requirement: str, policies: list[dict[str, Any]], *terms: str) -> str:
    """Select an exact source substring, preferring policy text for policy rules."""
    candidates = [str(item.get("rule_text", "")) for item in policies]
    candidates.append(requirement)
    for candidate in candidates:
        for term in terms:
            match = re.search(re.escape(term), candidate, re.IGNORECASE)
            if match:
                start = candidate.rfind(".", 0, match.start()) + 1
                end = candidate.find(".", match.end())
                return candidate[start : len(candidate) if end < 0 else end + 1].strip()
    fallback = requirement.strip()
    return fallback[:500] if len(fallback) >= 3 else "Requirement text"


def fake_extraction(requirement_text: str, policies: list[dict[str, Any]]) -> dict[str, Any]:
    """Create a valid deterministic extraction without inventing oracle values."""
    output = copy.deepcopy(RQ014_EXTRACTION_EXAMPLE)
    refs = {item.get("ref") for item in policies}
    for rule in output["rules"]:
        policy_ref = rule.get("policy_ref")
        if policy_ref and refs and policy_ref not in refs:
            matching = next((ref for ref in refs if isinstance(ref, str) and ref.startswith(policy_ref.split("@")[0])), None)
            rule["policy_ref"] = matching
        if rule["rule_key"] == "OT_THRESHOLD":
            rule["source_span"] = _source_span(requirement_text, policies, "480", "overtime")
        elif rule["rule_key"] == "MEAL_DEDUCTION":
            rule["source_span"] = _source_span(requirement_text, policies, "meal", "break")
        elif rule["rule_key"] == "SHIFT_SPAN":
            rule["source_span"] = _source_span(requirement_text, policies, "midnight", "overnight")
        else:
            rule["source_span"] = _source_span(requirement_text, policies, "overnight", "end")
    return output


class FakeProvider:
    """Provider-compatible fake that reads only the delimited prompt data."""

    provider = "fake"
    model = "fake-deterministic-v1"

    def complete(self, prompt: str) -> Completion:
        match = re.search(r"DATA_BEGIN\n(.*?)\nDATA_END", prompt, re.DOTALL)
        if match is None:
            raise ValueError("Fake provider prompt is missing DATA delimiters.")
        data = json.loads(match.group(1))
        result = fake_extraction(data["requirement_text"], data["policies"])
        return Completion(
            text=json.dumps(result),
            provider=self.provider,
            model=self.model,
        )
