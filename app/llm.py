"""Optional AI drafting of the policy's narrative sections via the Claude API.

When ANTHROPIC_API_KEY is set, the policy generator asks Claude to write the
Purpose / Scope / Roles / Compliance prose tailored to the selected CIS
benchmark. The **technical controls stay verbatim from CIS** — the model only
drafts the surrounding policy narrative, and is explicitly told not to invent
controls. If the key is missing or the call fails, the caller falls back to the
built-in static templates, so policy generation never depends on the API.
"""

from __future__ import annotations

import json
import os

# Per Anthropic guidance, default to the latest Opus; override for cost/latency
# (e.g. POLICY_LLM_MODEL=claude-sonnet-5).
MODEL = os.environ.get("POLICY_LLM_MODEL", "claude-opus-5")

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "purpose_intro": {"type": "string"},
        "purpose_points": {"type": "array", "items": {"type": "string"}},
        "purpose_aims": {"type": "array", "items": {"type": "string"}},
        "scope_intro": {"type": "string"},
        "scope_applies_to": {"type": "array", "items": {"type": "string"}},
        "scope_covers": {"type": "array", "items": {"type": "string"}},
        "roles": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "role": {"type": "string"},
                    "responsibilities": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["role", "responsibilities"],
            },
        },
        "compliance_intro": {"type": "string"},
        "compliance_exception_fields": {"type": "array", "items": {"type": "string"}},
        "compliance_enforcement": {"type": "string"},
    },
    "required": [
        "purpose_intro", "purpose_points", "purpose_aims",
        "scope_intro", "scope_applies_to", "scope_covers",
        "roles", "compliance_intro", "compliance_exception_fields",
        "compliance_enforcement",
    ],
}

_SYSTEM = (
    "You draft precise, professional corporate cybersecurity policy text for "
    "SABIC. Write in plain, formal enterprise English — no markdown, no "
    "bullet characters, one idea per string. Be specific to the technology at "
    "hand. Never invent technical security controls: the concrete controls "
    "come from the CIS Benchmark verbatim elsewhere in the document; your job "
    "is only the surrounding narrative (purpose, scope, roles, compliance)."
)


def available() -> bool:
    """True if an API key is configured and the SDK is importable."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def status() -> dict:
    return {"available": available(), "model": MODEL}


def generate_narrative(bench, meta) -> dict | None:
    """Return AI-drafted narrative sections, or None if unavailable/failed."""
    if not available():
        return None
    try:
        import anthropic

        client = anthropic.Anthropic()
        section_list = "; ".join(
            f"{s.number} {s.title}".strip() for s in bench.sections[:50]
        ) or "(no sections parsed)"
        prompt = (
            f"Draft the narrative sections of a SABIC cybersecurity hardening "
            f"standard for: {bench.title}"
            + (f" (version {bench.version})" if bench.version else "")
            + f".\nPlatform: {bench.platform or 'the in-scope technology'}.\n"
            f"The standard operationalises this CIS Benchmark; it contains "
            f"{bench.control_count} technical controls across these sections: "
            f"{section_list}.\n\n"
            "Write, tailored to this platform:\n"
            "- purpose_intro: one paragraph on why this standard exists.\n"
            "- purpose_points: 3-5 outcomes it ensures.\n"
            "- purpose_aims: 3-5 broader goals.\n"
            "- scope_intro: one paragraph on what it applies to.\n"
            "- scope_applies_to: 3-5 audiences/entities.\n"
            "- scope_covers: 3-5 activities it covers.\n"
            "- roles: 5-7 roles with 1-2 responsibilities each, relevant to "
            "operating and assuring this platform.\n"
            "- compliance_intro: one paragraph on how compliance is verified.\n"
            "- compliance_exception_fields: 3-5 items an exception record must "
            "capture.\n"
            "- compliance_enforcement: one paragraph on consequences of "
            "non-compliance.\n"
            "Do not restate individual CIS controls."
        )
        resp = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            thinking={"type": "disabled"},
            output_config={
                "effort": "low",
                "format": {"type": "json_schema", "schema": _SCHEMA},
            },
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        if getattr(resp, "stop_reason", None) == "refusal":
            return None
        text = next((b.text for b in resp.content if b.type == "text"), "")
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001 - any failure -> static fallback
        return None
