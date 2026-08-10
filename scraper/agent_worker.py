import os
import sys
import json
import sqlite3
import datetime
import logging
from logging.handlers import RotatingFileHandler
from openai import OpenAI
from config import API_KEY, LLM_MODEL

try:
    from config import API_BASE_URL
except ImportError:
    # Older config.py files predate the configurable endpoint.
    API_BASE_URL = None
from prompts import build_evaluation_prompt, get_outreach_draft_prompt
from scoring import score_listing

from evidence_extractor import EvidenceExtractor

# Set up logging
log_file = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "scraper.log",
)
os.makedirs(os.path.dirname(log_file), exist_ok=True)

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Clear existing handlers to prevent duplicates
for handler in list(root_logger.handlers):
    root_logger.removeHandler(handler)

formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
root_logger.addHandler(console_handler)

# File handler with rotation (max 5MB, keep 3 backups)
file_handler = RotatingFileHandler(
    log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
file_handler.setFormatter(formatter)
root_logger.addHandler(file_handler)

logger = logging.getLogger(__name__)

# Initialize OpenAI client. base_url stays None for OpenAI itself; pointing it at
# an OpenAI-compatible gateway (e.g. OpenRouter) is enough to switch providers.
openai_key = os.environ.get("OPENAI_API_KEY") or API_KEY
openai_base_url = os.environ.get("OPENAI_BASE_URL") or API_BASE_URL
client = OpenAI(api_key=openai_key, base_url=openai_base_url or None)


def _is_openai_reasoning_model(model=LLM_MODEL):
    """OpenAI's reasoning models reject `temperature` and rename the token cap."""
    return "gpt-5" in model or model.startswith("o1") or model.startswith("o3")


def get_response_text(response):
    """Returns the assistant text, tolerating an empty completion.

    Reasoning models (e.g. deepseek-v4-flash) spend part of the token budget on
    internal reasoning and return `content: None` when the cap is hit before any
    visible text is produced. Callers used to dereference `.strip()` on that None
    and die with an AttributeError, so normalise it to an empty string here and
    let the existing validation/retry path handle it.
    """
    choice = response.choices[0]
    content = choice.message.content
    if not content:
        logger.warning(
            "Model returned empty content (finish_reason=%s). "
            "This usually means max_tokens was exhausted by reasoning tokens.",
            getattr(choice, "finish_reason", "unknown"),
        )
        return ""
    return content.strip()


def build_llm_kwargs(messages, max_tokens, temperature=0.0):
    """Builds chat-completion kwargs matching the configured model's dialect.

    Reasoning models take `max_completion_tokens` and no temperature; every other
    model (including those served via OpenRouter) takes `max_tokens`.
    """
    kwargs = {"model": LLM_MODEL, "messages": messages}
    if _is_openai_reasoning_model():
        kwargs["max_completion_tokens"] = max_tokens
    else:
        kwargs["max_tokens"] = max_tokens
        kwargs["temperature"] = temperature
    return kwargs


extractor = EvidenceExtractor()

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "scraper.db",
)


def get_db_connection():
    # SQLite connection with high busy_timeout to support parallel worker writes
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def log_listing_analysis(
    listing_id,
    prompt,
    initial_response,
    validation_errors=None,
    retry_prompt=None,
    retry_response=None,
    parsed_json=None,
    score_contributions=None,
    final_score=None,
):
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data",
        "logs",
    )
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"{listing_id}_{ts}.log")

    with open(log_path, "w", encoding="utf-8") as f:
        f.write(
            f"=== ANALYSIS RUN: {datetime.datetime.now(datetime.timezone.utc).isoformat()} ===\n\n"
        )
        f.write("=== INITIAL PROMPT ===\n")
        f.write(prompt)
        f.write("\n\n=== INITIAL RESPONSE ===\n")
        f.write(initial_response or "")
        f.write("\n")

        if validation_errors:
            f.write("\n=== VALIDATION ERRORS ===\n")
            f.write("\n".join(validation_errors))
            f.write("\n")

        if retry_prompt:
            f.write("\n=== RETRY PROMPT ===\n")
            f.write(retry_prompt)
            f.write("\n\n=== RETRY RESPONSE ===\n")
            f.write(retry_response or "")
            f.write("\n")

        if parsed_json is not None:
            f.write("\n=== PARSED JSON AFTER SANITIZATION ===\n")
            f.write(json.dumps(parsed_json, indent=2))
            f.write("\n")
        if score_contributions is not None:
            f.write("\n=== SCORE CONTRIBUTIONS ===\n")
            for cid, contrib in score_contributions.items():
                if isinstance(contrib, dict) and "satisfied_if" in contrib:
                    f.write(
                        f"- {cid}: value='{contrib['value']}', expected='{contrib['satisfied_if']}', importance={contrib['importance']}, satisfied={contrib['satisfied']}, contribution={contrib['contribution']}\n"
                    )
                else:
                    f.write(f"- {cid}: {contrib}\n")
            f.write("\n")

        if final_score is not None:
            f.write(f"\n=== FINAL NICENESS SCORE: {final_score} ===\n")


def log_conversation_analysis(listing_id, prompt, response):
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data",
        "logs",
    )
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"{listing_id}_{ts}_conversation.log")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(
            f"=== CONVERSATION ANALYSIS RUN: {datetime.datetime.now(datetime.timezone.utc).isoformat()} ===\n\n"
        )
        f.write("=== PROMPT ===\n")
        f.write(prompt)
        f.write("\n\n=== RESPONSE ===\n")
        f.write(response or "")
        f.write("\n")


def log_outreach_draft(listing_id, prompt, response):
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data",
        "logs",
    )
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"{listing_id}_{ts}_outreach.log")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(
            f"=== OUTREACH DRAFT RUN: {datetime.datetime.now(datetime.timezone.utc).isoformat()} ===\n\n"
        )
        f.write("=== PROMPT ===\n")
        f.write(prompt)
        f.write("\n\n=== RESPONSE ===\n")
        f.write(response or "")
        f.write("\n")


def process_unprocessed_listings(target_listing_id=None, campaign_id=None):
    """Finds all unprocessed listings (or a specific single listing), extracts attributes using OpenAI, and scores them"""
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Query listings that have a profile assigned and haven't been LLM processed
    if target_listing_id:
        cursor.execute(
            """
            SELECT l.id, l.title, l.detailed_description, l.details, l.search_id, k.item_json, k.expert_knowledge,
                   k.good_reference_description, k.bad_reference_description
            FROM listings l
            JOIN searches s ON l.search_id = s.id
            JOIN campaigns c ON s.campaign_id = c.id
            LEFT JOIN knowledge_sets k ON s.knowledge_set_id = k.id
            WHERE l.id = ?
        """,
            (target_listing_id,),
        )
    else:
        if campaign_id is not None:
            cursor.execute(
                """
                SELECT l.id, l.title, l.detailed_description, l.details, l.search_id, k.item_json, k.expert_knowledge,
                       k.good_reference_description, k.bad_reference_description
                FROM listings l
                JOIN searches s ON l.search_id = s.id
                JOIN campaigns c ON s.campaign_id = c.id
                LEFT JOIN knowledge_sets k ON s.knowledge_set_id = k.id
                WHERE s.enabled = 1 AND c.id = ? AND (
                    l.llm_processed = 0 OR 
                    l.last_ai_evaluated_at IS NULL OR 
                    l.last_description_changed_at > l.last_ai_evaluated_at
                )
            """,
                (campaign_id,),
            )
        else:
            cursor.execute(
                """
                SELECT l.id, l.title, l.detailed_description, l.details, l.search_id, k.item_json, k.expert_knowledge,
                       k.good_reference_description, k.bad_reference_description
                FROM listings l
                JOIN searches s ON l.search_id = s.id
                JOIN campaigns c ON s.campaign_id = c.id
                LEFT JOIN knowledge_sets k ON s.knowledge_set_id = k.id
                WHERE s.enabled = 1 AND (
                    l.llm_processed = 0 OR 
                    l.last_ai_evaluated_at IS NULL OR 
                    l.last_description_changed_at > l.last_ai_evaluated_at
                )
            """
            )
    listings = cursor.fetchall()

    if not listings:
        logger.info("No unprocessed listings found.")
        conn.close()
        return

    logger.info(f"Processing {len(listings)} listings...")

    for listing in listings:
        listing_id = listing["id"]
        title = listing["title"]
        description = listing["detailed_description"] or ""
        details_text = ""
        try:
            details_obj = json.loads(listing["details"] or "{}")
            if details_obj:
                details_text = "\n".join(
                    [f"- {k}: {v}" for k, v in details_obj.items()]
                )
        except Exception as e:
            logger.warning(f"Failed to parse listing details for LLM prompt: {str(e)}")

        logger.info(f"Analyzing: {title} (ID: {listing_id})")

        try:
            item_config = json.loads(listing["item_json"] or "{}")
            fields_list = item_config.get("fields", [])
            if fields_list:
                criteria_list = fields_list
            else:
                # Support both old flat extraction_criteria and new split schema
                criteria_list = item_config.get(
                    "extraction_criteria"
                ) or item_config.get(
                    "explicit_positive_criteria", []
                ) + item_config.get("explicit_negative_criteria", [])
            scoring_model = item_config.get("scoring_model", {})
        except Exception as e:
            logger.error(f"Error parsing item_json for listing {listing_id}: {str(e)}")
            continue

        # Check for legacy non-boolean criteria/weights in python (only if NOT using unified fields)
        is_legacy_profile = False
        legacy_details = []
        if not fields_list:
            for c in criteria_list:
                if c.get("type") != "boolean":
                    is_legacy_profile = True
                    legacy_details.append(
                        f"Criterion '{c.get('id')}' has unsupported type '{c.get('type')}' (only 'boolean' is supported)."
                    )

            weights = scoring_model.get("weights", {})
            for cid, w in weights.items():
                if w and not isinstance(w.get("satisfied_if"), bool):
                    is_legacy_profile = True
                    legacy_details.append(
                        f"Weight '{cid}' has unsupported satisfied_if value '{w.get('satisfied_if')}' (must be a boolean)."
                    )

        if is_legacy_profile:
            err_msg = "; ".join(legacy_details)
            logger.error(
                f"Unsupported legacy profile for listing {listing_id}: {err_msg}"
            )

            facts_envelope = {
                "criteria": {},
                "highlights": [],
                "draft_message": "",
                "_full_info_obtained": False,
                "_unsupported_legacy_profile": True,
                "_legacy_error_details": f"Unsupported legacy profile: {err_msg}",
            }

            cursor.execute(
                """
                UPDATE listings 
                SET llm_processed = 1,
                    llm_processed_time = ?,
                    last_ai_evaluated_at = ?,
                    full_info_obtained = 0,
                    extracted_facts = ?,
                    niceness_score = 0,
                    status = 'Error'
                WHERE id = ?
            """,
                (
                    datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    json.dumps(facts_envelope),
                    listing_id,
                ),
            )
            conn.commit()
            continue

        item_json_str = listing["item_json"] or "{}"
        prompt = build_evaluation_prompt(
            title,
            details_text,
            description,
            item_json_str,
            listing["expert_knowledge"],
            good_reference_description=listing["good_reference_description"],
            bad_reference_description=listing["bad_reference_description"],
        )

        try:
            messages = [{"role": "user", "content": prompt}]

            kwargs = build_llm_kwargs(messages, max_tokens=32000)
            response = client.chat.completions.create(**kwargs)
            response_text = get_response_text(response)

            initial_response_text = response_text
            retry_prompt_val = None
            retry_response_val = None
            initial_validation_errors = None

            extracted_data, validation_errors = extractor.extract(
                response_text, criteria_list
            )

            # Bounded One-Shot Retry
            if validation_errors:
                initial_validation_errors = list(validation_errors)
                logger.warning(
                    f"Validation failed for listing {listing_id}. Errors: {validation_errors}. Retrying one-shot..."
                )
                errors_str = "\n".join([f"- {err}" for err in validation_errors])
                retry_prompt = (
                    f"{prompt}\n\n"
                    "--- VALIDATION FAILURE ---\n"
                    "Your previous response failed validation with the following errors:\n"
                    f"{errors_str}\n\n"
                    "--- PREVIOUS RESPONSE ---\n"
                    f"{response_text}\n\n"
                    "Please correct the errors and output the complete corrected JSON strictly between START_JSON and END_JSON lines conforming to the TARGET JSON SCHEMA."
                )
                retry_prompt_val = retry_prompt

                retry_messages = []
                if _is_openai_reasoning_model():
                    retry_messages.append({"role": "user", "content": retry_prompt})
                else:
                    retry_messages.append(
                        {
                            "role": "system",
                            "content": "You are a precise, objective product analyst.",
                        }
                    )
                    retry_messages.append({"role": "user", "content": retry_prompt})

                retry_kwargs = build_llm_kwargs(retry_messages, max_tokens=32000)

                try:
                    response = client.chat.completions.create(**retry_kwargs)
                    response_text = get_response_text(response)
                    retry_response_val = response_text
                    extracted_data, validation_errors = extractor.extract(
                        response_text, criteria_list
                    )
                    if validation_errors:
                        logger.error(
                            f"Validation failed after retry for listing {listing_id}. Errors: {validation_errors}. Proceeding with best-effort parsing."
                        )
                except Exception as retry_err:
                    logger.error(
                        f"Error during retry for listing {listing_id}: {str(retry_err)}"
                    )

            if not extracted_data or not isinstance(extracted_data, dict):
                extracted_data = {}

            criteria_part = extracted_data.get("criteria", {})
            if not isinstance(criteria_part, dict):
                criteria_part = {}

            highlights_part = extracted_data.get("highlights", [])
            if not isinstance(highlights_part, list):
                highlights_part = []

            high_value_unknowns = extracted_data.get("high_value_unknowns", [])
            if not isinstance(high_value_unknowns, list):
                high_value_unknowns = []

            risk_flags = extracted_data.get("risk_flags", [])
            if not isinstance(risk_flags, list):
                risk_flags = []

            draft_message = extracted_data.get("draft_message", "")
            full_info_obtained = extracted_data.get("_full_info_obtained", False)

            # Populate and normalize criteria list
            normalized_criteria = {}
            for c in criteria_list:
                cid = c["id"]
                c_val = criteria_part.get(cid)
                if not isinstance(c_val, dict):
                    c_val = {}

                value = c_val.get("value")
                if value is None:
                    value = extracted_data.get(cid)
                if value not in ["yes", "no", "unknown"]:
                    if value is True or (
                        isinstance(value, str) and value.lower() in ["true", "yes"]
                    ):
                        value = "yes"
                    elif value is False or (
                        isinstance(value, str) and value.lower() in ["false", "no"]
                    ):
                        value = "no"
                    else:
                        value = "unknown"

                evidence_quote = c_val.get("evidence_quote", "")
                if not isinstance(evidence_quote, str):
                    evidence_quote = (
                        str(evidence_quote) if evidence_quote is not None else ""
                    )

                reasoning = c_val.get("reasoning", "")
                if not isinstance(reasoning, str):
                    reasoning = str(reasoning) if reasoning is not None else ""

                normalized_criteria[cid] = {
                    "value": value,
                    "evidence_quote": evidence_quote,
                    "reasoning": reasoning,
                }

            # Parse dimensions
            dimensions_part = extracted_data.get("dimensions", {})
            if not isinstance(dimensions_part, dict):
                dimensions_part = {}

            expected_dims = [
                "trustworthiness",
                "transparency",
                "conditionConfidence",
                "documentationQuality",
                "hiddenRiskSuspicion",
                "marketAboveAverageSignal",
            ]
            normalized_dimensions = {}
            for dim_key in expected_dims:
                dim_data = dimensions_part.get(dim_key)
                raw_score = 3
                reasoning = ""
                if isinstance(dim_data, dict):
                    raw_score = dim_data.get("score", 3)
                    reasoning = dim_data.get("reasoning", "")
                elif isinstance(dim_data, (int, float)):
                    raw_score = dim_data

                try:
                    raw_score = int(float(raw_score))
                except (ValueError, TypeError):
                    raw_score = 3
                raw_score = max(1, min(5, raw_score))

                normalized_dimensions[dim_key] = {
                    "score": raw_score,
                    "reasoning": str(reasoning),
                }

            # Parse reference comparison
            ref_comp_part = extracted_data.get("reference_comparison", {})
            if not isinstance(ref_comp_part, dict):
                ref_comp_part = {}

            closer_to = ref_comp_part.get("closer_to", "mixed")
            if closer_to not in ["good", "bad", "mixed"]:
                closer_to = "mixed"
            ref_reasoning = ref_comp_part.get("reasoning", "")

            normalized_ref_comp = {
                "closer_to": closer_to,
                "reasoning": str(ref_reasoning),
            }

            # Score: route by unified scoring engine
            transient_envelope = {
                "criteria": normalized_criteria,
                "dimensions": normalized_dimensions,
                "reference_comparison": normalized_ref_comp,
                "high_value_unknowns": high_value_unknowns,
                "risk_flags": risk_flags,
            }
            scoring_res = score_listing(transient_envelope, item_config)
            score = scoring_res.score
            contributions = scoring_res.contributions

            status = "New"
            full_info = (
                1
                if (
                    full_info_obtained is True
                    or all(
                        v["value"] != "unknown" for v in normalized_criteria.values()
                    )
                )
                else 0
            )

            # Reconstruct full nested facts envelope for the DB
            facts_envelope = {
                "criteria": normalized_criteria,
                "dimensions": normalized_dimensions,
                "reference_comparison": normalized_ref_comp,
                "highlights": highlights_part,
                "high_value_unknowns": high_value_unknowns,
                "risk_flags": risk_flags,
                "draft_message": draft_message,
                "_full_info_obtained": bool(full_info),
                "_audit": {"_raw_model_response": response_text},
            }

            # Update Listing
            cursor.execute(
                """
                UPDATE listings 
                SET llm_processed = 1,
                    llm_processed_time = ?,
                    last_ai_evaluated_at = ?,
                    full_info_obtained = ?,
                    extracted_facts = ?,
                    niceness_score = ?,
                    status = ?
                WHERE id = ?
            """,
                (
                    datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    full_info,
                    json.dumps(facts_envelope),
                    score,
                    status,
                    listing_id,
                ),
            )
            conn.commit()

            log_listing_analysis(
                listing_id=listing_id,
                prompt=prompt,
                initial_response=initial_response_text,
                validation_errors=initial_validation_errors,
                retry_prompt=retry_prompt_val,
                retry_response=retry_response_val,
                parsed_json=facts_envelope,
                score_contributions=contributions,
                final_score=score,
            )

            logger.info(
                f"Successfully processed and scored listing {listing_id}: Score = {score}, Status = {status}"
            )

        except Exception as e:
            logger.error(f"Error processing listing {listing_id} with OpenAI: {str(e)}")

    conn.close()


def generate_outreach_draft(listing_id):
    """Generates a first-touch personalized outreach draft based on missing (unknown) attributes"""
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT l.title, l.detailed_description, l.details, l.extracted_facts, k.item_json, k.expert_knowledge 
        FROM listings l
        JOIN searches s ON l.search_id = s.id
        JOIN campaigns c ON s.campaign_id = c.id
        LEFT JOIN knowledge_sets k ON s.knowledge_set_id = k.id
        WHERE l.id = ?
    """,
        (listing_id,),
    )
    row = cursor.fetchone()

    if not row:
        print("Error: Listing or Profile not found.")
        conn.close()
        sys.exit(1)

    title = row["title"]
    description = row["detailed_description"] or ""
    try:
        details_obj = json.loads(row["details"] or "{}")
        if details_obj:
            details_text = "\n".join([f"- {k}: {v}" for k, v in details_obj.items()])
            description = f"Key attributes/details:\n{details_text}\n\nDescription:\n{description}"
    except Exception as e:
        print(f"Failed to parse listing details for outreach draft: {str(e)}")

    try:
        facts = json.loads(row["extracted_facts"] or "{}")
        item_config = json.loads(row["item_json"] or "{}")
        strategy = item_config.get("outreach_strategy", {})
    except Exception as e:
        print(f"Error parsing listing metrics: {str(e)}")
        conn.close()
        sys.exit(1)

    # Check for missing/unknown criteria
    missing_criteria = [k for k, v in facts.items() if v == "unknown"]

    # Generate outreach prompt
    prompt = get_outreach_draft_prompt(
        title, description, facts, strategy, missing_criteria, row["expert_knowledge"]
    )

    try:
        kwargs = build_llm_kwargs(
            [
                {
                    "role": "system",
                    "content": "You write elegant, friendly outreach messages for prospective buyers.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=2000,
            temperature=0.7,
        )
        response = client.chat.completions.create(**kwargs)
        draft_message = get_response_text(response)
        print(draft_message)
        try:
            log_outreach_draft(listing_id, prompt, draft_message)
        except Exception as log_err:
            logger.warning(
                f"Failed to log outreach draft for listing {listing_id}: {str(log_err)}"
            )
    except Exception as e:
        print(f"Error generating outreach draft from OpenAI: {str(e)}")
        sys.exit(1)

    conn.close()


def analyze_conversation(listing_id):
    """Analyzes dynamic chats/negotiations to clarify outstanding unknowns in extracted facts"""
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. Fetch listing, its facts, and matching profile extraction criteria
    cursor.execute(
        """
        SELECT l.extracted_facts, l.search_id, k.item_json
        FROM listings l
        JOIN searches s ON l.search_id = s.id
        LEFT JOIN knowledge_sets k ON s.knowledge_set_id = k.id
        WHERE l.id = ?
    """,
        (listing_id,),
    )
    row = cursor.fetchone()

    if not row:
        logger.warning(
            f"No listing/profile found for conversation analysis on listing {listing_id}"
        )
        conn.close()
        return

    try:
        facts_envelope = json.loads(row["extracted_facts"] or "{}")
        if isinstance(facts_envelope, dict) and "criteria" in facts_envelope:
            facts = facts_envelope["criteria"]
            dimensions = facts_envelope.get("dimensions", {})
            reference_comparison = facts_envelope.get("reference_comparison", {})
        else:
            facts = facts_envelope
            dimensions = {}
            reference_comparison = {}
        item_config = json.loads(row["item_json"] or "{}")
        criteria_list = item_config.get("extraction_criteria", [])
    except Exception as e:
        logger.error(f"Error parsing metadata for listing {listing_id}: {str(e)}")
        conn.close()
        return

    # Check if there are any unknowns to resolve
    unknown_keys = []
    for k, v in facts.items():
        if isinstance(v, dict) and v.get("value") == "unknown":
            unknown_keys.append(k)
        elif v == "unknown":
            unknown_keys.append(k)

    if not unknown_keys:
        logger.info(f"No unknown criteria to resolve for listing {listing_id}.")
        conn.close()
        return

    # 2. Fetch synced messages
    cursor.execute(
        """
        SELECT sender_name, is_outbound, message_text 
        FROM messages 
        WHERE listing_id = ? 
        ORDER BY message_date ASC
    """,
        (listing_id,),
    )
    msgs = cursor.fetchall()

    if not msgs:
        logger.info(f"No synced messages found to analyze for listing {listing_id}.")
        conn.close()
        return

    # Format chat log
    chat_log = ""
    for m in msgs:
        sender = "Buyer" if m["is_outbound"] else (m["sender_name"] or "Seller")
        chat_log += f"{sender}: {m['message_text']}\n"

    # Build dynamic questions prompt
    target_criteria = [c for c in criteria_list if c["id"] in unknown_keys]
    criteria_instructions = ""
    for c in target_criteria:
        criteria_instructions += f"- ID: '{c['id']}'\n  Type: {c.get('type', 'boolean')}\n  Instruction: {c['description']}\n\n"

    prompt = (
        "You are an expert product analyst reviewing a conversation between a prospective buyer and seller.\n\n"
        "Here is the chat history:\n"
        f"{chat_log}\n"
        "And here are the attributes currently marked as 'unknown' that we want to resolve:\n"
        f"{criteria_instructions}"
        "Your task is to analyze the seller's replies in the chat history. "
        "Determine if the seller has clarified the value of any of these attributes.\n\n"
        "Provide your answers in a raw, valid JSON block. "
        "Do not include any explanations outside the JSON block. "
        "Keep the attribute value as 'unknown' if it has not been clarified.\n\n"
        "Format:\n"
        "```json\n"
        "{\n"
        + ",\n".join([f'  "{k}": true/false/"unknown"' for k in unknown_keys])
        + "\n"
        "}\n"
        "```"
    )

    try:
        kwargs = build_llm_kwargs(
            [
                {
                    "role": "system",
                    "content": "You are a precise, objective chat analyzer.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=2000,
        )
        response = client.chat.completions.create(**kwargs)
        response_text = get_response_text(response)
        try:
            log_conversation_analysis(listing_id, prompt, response_text)
        except Exception as log_err:
            logger.warning(
                f"Failed to log conversation analysis for listing {listing_id}: {str(log_err)}"
            )
        updated_data = extractor.extract_json_block(response_text)

        if not updated_data:
            logger.warning(
                f"Could not extract JSON from conversation analysis for listing {listing_id}."
            )
            conn.close()
            return

        # Update facts map
        changes_made = False
        for k, v in updated_data.items():
            if k in facts and v != "unknown":
                val = "unknown"
                if v is True or (isinstance(v, str) and v.lower() in ["true", "yes"]):
                    val = "yes"
                elif v is False or (
                    isinstance(v, str) and v.lower() in ["false", "no"]
                ):
                    val = "no"

                # Check if it was previously unknown
                is_prev_unknown = False
                if isinstance(facts[k], dict):
                    if facts[k].get("value") == "unknown":
                        is_prev_unknown = True
                elif facts[k] == "unknown":
                    is_prev_unknown = True

                if is_prev_unknown and val != "unknown":
                    if isinstance(facts[k], dict):
                        facts[k]["value"] = val
                        facts[k]["evidence_quote"] = "Clarified in chat conversation"
                        facts[k]["reasoning"] = f"Resolved via chat to: {val}."
                    else:
                        facts[k] = {
                            "value": val,
                            "evidence_quote": "Clarified in chat conversation",
                            "reasoning": f"Resolved via chat to: {val}.",
                        }
                    changes_made = True
                    logger.info(
                        f"Resolved unknown criterion '{k}' to '{val}' for listing {listing_id}"
                    )

        if changes_made:
            # Recalculate score using unified scoring engine
            scoring_res = score_listing(facts_envelope, item_config)
            score = scoring_res.score

            status = "Negotiating"

            # Check if all criteria are now known
            full_info = True
            for k, v in facts.items():
                if isinstance(v, dict):
                    if v.get("value") == "unknown":
                        full_info = False
                elif v == "unknown":
                    full_info = False

            # Put back into envelope
            if isinstance(facts_envelope, dict):
                facts_envelope["criteria"] = facts
                facts_envelope["_full_info_obtained"] = full_info
            else:
                facts_envelope = {
                    "criteria": facts,
                    "dimensions": dimensions,
                    "reference_comparison": reference_comparison,
                    "highlights": [],
                    "draft_message": "",
                    "_full_info_obtained": full_info,
                }

            cursor.execute(
                """
                UPDATE listings 
                SET extracted_facts = ?,
                    niceness_score = ?,
                    status = ?,
                    full_info_obtained = ?
                WHERE id = ?
            """,
                (
                    json.dumps(facts_envelope),
                    score,
                    status,
                    1 if full_info else 0,
                    listing_id,
                ),
            )
            conn.commit()
            logger.info(
                f"Updated listing {listing_id} score to {score} after resolved chat unknowns."
            )

    except Exception as e:
        logger.error(
            f"Error during conversation analysis for listing {listing_id}: {str(e)}"
        )

    conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "Usage: python3 agent_worker.py [process [--campaign-id <id>] | draft <listing_id> | analyze <listing_id>]"
        )
        sys.exit(1)

    command = sys.argv[1]

    if command == "process":
        campaign_id = None
        target_listing_id = None

        args = sys.argv[2:]
        i = 0
        while i < len(args):
            if args[i] == "--campaign-id":
                if i + 1 < len(args):
                    try:
                        campaign_id = int(args[i + 1])
                    except ValueError:
                        pass
                    i += 2
                else:
                    i += 1
            else:
                target_listing_id = args[i]
                i += 1

        process_unprocessed_listings(target_listing_id, campaign_id=campaign_id)
    elif command == "draft":
        if len(sys.argv) < 3:
            print("Usage: python3 agent_worker.py draft <listing_id>")
            sys.exit(1)
        generate_outreach_draft(sys.argv[2])
    elif command == "analyze":
        if len(sys.argv) < 3:
            print("Usage: python3 agent_worker.py analyze <listing_id>")
            sys.exit(1)
        analyze_conversation(sys.argv[2])
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
