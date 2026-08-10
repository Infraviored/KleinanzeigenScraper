import os
import json

_INTERNAL_PROMPT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "prompts",
    "internal_prompt.md",
)


_LEGACY_CRITERIA_VALUE_SPEC = """- Criteria:
  - yes = explicitly supported in the listing
  - no = explicitly contradicted OR explicit warning present
  - unknown = not clearly stated"""


def _build_criteria_value_spec(fields_list):
    """Describes the value format the model must emit for each criterion.

    Legacy profiles are boolean-only, so a single yes/no/unknown rule covers them.
    Unified `fields` profiles mix numbers, tiers and enums; without a per-field
    format the model answers yes/no for everything and the typed values are
    rejected downstream as invalid_number / invalid_tier.
    """
    if not fields_list:
        return _LEGACY_CRITERIA_VALUE_SPEC

    lines = [
        "- Criteria: each criterion below states the exact value format it accepts.",
        "  Emit the literal value, never yes/no, unless the criterion is boolean.",
        "  Use null when the listing does not state the fact (do not guess).",
    ]

    for field in fields_list:
        fid = field.get("id")
        if not fid:
            continue

        ftype = field.get("type", "boolean")
        label = field.get("label") or fid
        wants = field.get("buyer_wants") or {}

        if ftype == "boolean":
            fmt = '"yes", "no" or "unknown"'
        elif ftype == "number":
            fmt = "a bare JSON number (no units, no ranges, no text) or null"
        elif ftype == "tier":
            fmt = "an integer from 1 to 5 or null"
        elif ftype == "enum":
            allowed = wants.get("preferred", []) + wants.get("excluded", [])
            allowed_str = ", ".join(f'"{option}"' for option in allowed)
            fmt = (
                f"exactly one of [{allowed_str}] or null"
                if allowed_str
                else "a single short lowercase label or null"
            )
        else:
            fmt = "a short string (max 120 chars) or null"

        lines.append(f'  - "{fid}" ({label}) -> {fmt}')

    return "\n".join(lines)


def build_evaluation_prompt(
    title,
    details_text,
    description,
    item_json_str,
    expert_knowledge,
    good_reference_description=None,
    bad_reference_description=None,
):
    """Fill internal_prompt.md placeholders, build JSON skeleton, and return the complete prompt string."""
    with open(_INTERNAL_PROMPT_PATH, encoding="utf-8") as f:
        template = f.read()

    # Build the JSON skeleton dynamically from criteria (supports old, new split schema, and unified fields)
    criteria_list = []
    fields_list = []
    dimensions_enabled = True
    try:
        if item_json_str:
            item_config = json.loads(item_json_str)
            fields_list = item_config.get("fields", [])
            dimensions_enabled = item_config.get("dimensions_enabled", True)
            if not fields_list:
                criteria_list = item_config.get(
                    "extraction_criteria"
                ) or item_config.get(
                    "explicit_positive_criteria", []
                ) + item_config.get("explicit_negative_criteria", [])
    except Exception:
        pass

    skeleton_criteria = {}
    if fields_list:
        for f in fields_list:
            fid = f.get("id")
            ftype = f.get("type", "boolean")
            if fid:
                if ftype == "boolean":
                    skeleton_criteria[fid] = {
                        "value": "unknown",
                        "evidence_quote": "",
                        "reasoning": "",
                    }
                elif ftype in ("number", "tier"):
                    skeleton_criteria[fid] = {
                        "value": None,
                        "evidence_quote": "",
                        "reasoning": "",
                    }
                elif ftype == "enum":
                    skeleton_criteria[fid] = {
                        "value": None,
                        "evidence_quote": "",
                        "reasoning": "",
                    }
                else:  # text
                    skeleton_criteria[fid] = {
                        "value": None,
                        "evidence_quote": "",
                    }
    else:
        for c in criteria_list:
            cid = c.get("id")
            if cid:
                skeleton_criteria[cid] = {
                    "value": "unknown",
                    "evidence_quote": "",
                    "reasoning": "",
                }

    criteria_value_spec = _build_criteria_value_spec(fields_list)

    skeleton = {
        "criteria": skeleton_criteria,
    }

    if dimensions_enabled:
        skeleton["dimensions"] = {
            "trustworthiness": {"score": 1, "reasoning": ""},
            "transparency": {"score": 1, "reasoning": ""},
            "conditionConfidence": {"score": 1, "reasoning": ""},
            "documentationQuality": {"score": 1, "reasoning": ""},
            "hiddenRiskSuspicion": {"score": 1, "reasoning": ""},
            "marketAboveAverageSignal": {"score": 1, "reasoning": ""},
        }
        skeleton["reference_comparison"] = {"closer_to": "mixed", "reasoning": ""}
        skeleton["high_value_unknowns"] = []
        skeleton["risk_flags"] = []

    skeleton["_full_info_obtained"] = False

    skeleton_str = json.dumps(skeleton, indent=2)

    filled = (
        template.replace("{{EXPERT_KNOWLEDGE}}", expert_knowledge or "")
        .replace("{{ITEM_JSON}}", item_json_str)
        .replace("{{GOOD_REFERENCE_DESCRIPTION}}", good_reference_description or "")
        .replace("{{BAD_REFERENCE_DESCRIPTION}}", bad_reference_description or "")
        .replace("{{LISTING_TITLE}}", title)
        .replace("{{LISTING_DETAILS}}", details_text)
        .replace("{{LISTING_DESCRIPTION}}", description)
        .replace("{{JSON_SKELETON}}", skeleton_str)
        .replace("{{CRITERIA_VALUE_SPEC}}", criteria_value_spec)
    )
    return filled


def get_outreach_draft_prompt(
    title,
    description,
    extracted_facts,
    outreach_strategy,
    missing_criteria,
    expert_knowledge=None,
):
    """Generates the prompt for the Worker AI to draft a tailored first-touch outreach message"""
    questions_block = ""
    for q in outreach_strategy.get("questions", []):
        if q.get("target_criterion") in missing_criteria:
            questions_block += (
                f"- Ask about {q.get('target_criterion')}: {q.get('question_text')}\n"
            )

    gk_block = ""
    if expert_knowledge:
        gk_block = f"General Domain & Expert Knowledge Rules:\n{expert_knowledge}\n\n"

    return (
        "You are a friendly, knowledgeable buyer interested in purchasing the product in the listing below.\n\n"
        f"{gk_block}"
        f"Listing Title: {title}\n"
        f"Listing Description:\n{description}\n\n"
        "Outreach Strategy Guidelines:\n"
        f"- Tone: {outreach_strategy.get('tone', 'friendly, casual, polite')}\n"
        f"- Opening Hook: {outreach_strategy.get('opening_hook', 'Hi, I am interested in your item.')}\n\n"
        "Specific Questions to Inquire About:\n"
        f"{questions_block}\n"
        "Your task is to draft a cohesive, highly natural message in German (or the listing's native language) "
        "asking for the item. Smoothly blend the opening hook, showing you are informed about the item, "
        "with the questions about the missing details. Keep the message concise, inviting the seller to chat "
        "rather than sounding like an interrogation. Do not use generic placeholders. Output only the message text itself."
    )
