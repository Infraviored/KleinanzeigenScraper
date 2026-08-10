from dataclasses import dataclass
from typing import Dict, Any, Tuple
import logging

logger = logging.getLogger(__name__)


@dataclass
class ScoringResult:
    score: int
    criteria_score: float
    dimensions_score: float
    contributions: Dict[str, Any]
    is_new_schema: bool
    # Field ids of hard constraints this listing violates. Non-empty means the
    # listing is disqualified rather than merely poorly rated.
    disqualified_by: Tuple[str, ...] = ()
    # Hard constraints the listing could not be shown to satisfy because the
    # fact is missing. Distinct from a violation: these are worth asking about,
    # not discarding.
    unverified_constraints: Tuple[str, ...] = ()

    @property
    def disqualified(self) -> bool:
        return bool(self.disqualified_by)


_UNMET_STATUSES = {"violated", "invalid_number", "invalid_tier"}
_UNKNOWN_STATUSES = {"missing", "missing_critical", "penalized_missing", "neutral"}


def evaluate_hard_constraints(contributions: Dict[str, Any]):
    """Splits unmet hard constraints into violations and unverifiable ones.

    The distinction decides what happens to the listing. A violation is a fact
    that rules it out. A missing value only means the seller did not say — worth
    raising as a question, but discarding on silence would throw away most of a
    market where descriptions are written by amateurs.
    """
    violated, unverified = [], []

    for fid, contribution in contributions.items():
        if not isinstance(contribution, dict) or not contribution.get("hard"):
            continue
        status = contribution.get("status")
        if status in _UNMET_STATUSES:
            violated.append(fid)
        elif status in _UNKNOWN_STATUSES:
            unverified.append(fid)

    return tuple(violated), tuple(unverified)


def is_satisfied(value, satisfied_if):
    """Checks if the extracted criterion value matches the satisfied_if target.
    unknown always returns False regardless of satisfied_if — silence is not safe."""
    if value is None or satisfied_if is None:
        return False

    def normalize(val):
        if isinstance(val, bool):
            return val
        s = str(val).strip().lower()
        if s in ("yes", "y", "true", "ja", "j"):
            return True
        if s in ("no", "n", "false", "nein"):
            return False
        try:
            if s.isdigit():
                return int(s)
            return float(s)
        except ValueError:
            pass
        return s

    norm_val = normalize(value)

    # unknown never satisfies any criterion — not even risk guardrails
    if norm_val == "unknown" or norm_val is None:
        return False

    norm_target = normalize(satisfied_if)
    if norm_target == "unknown" or norm_target is None:
        return False

    if isinstance(norm_val, bool) and isinstance(norm_target, bool):
        return norm_val == norm_target

    if isinstance(norm_val, (int, float)) and isinstance(norm_target, (int, float)):
        return norm_val == norm_target

    if isinstance(norm_val, bool) and isinstance(norm_target, (int, float)):
        return norm_val == (norm_target != 0)
    if isinstance(norm_target, bool) and isinstance(norm_val, (int, float)):
        return norm_target == (norm_val != 0)

    return str(norm_val) == str(norm_target)


def calculate_blended_score(
    criteria: dict, weights: dict, dimensions: dict
) -> Tuple[int, float, float, Dict[str, Any]]:
    """Calculates the blended score: 65% criteria, 35% dimensions, with a coverage factor.

    Coverage factor: the fraction of all criteria that returned an explicit yes/no (not unknown).
    A listing with mostly unknowns is penalised — it cannot score highly on vague silence.
    Coverage below 40% caps the effective score at 50. Coverage scales linearly 40%→100%.
    """
    # 1. Criteria score
    total_possible_weight = 0
    satisfied_weight = 0
    contributions = {}

    resolved_count = 0
    total_count = max(len(weights), 1)

    for cid, cfg in weights.items():
        importance = cfg.get("importance", 0)
        satisfied_if = cfg.get("satisfied_if")
        total_possible_weight += importance

        c_val = criteria.get(cid)
        if not isinstance(c_val, dict):
            contributions[cid] = {
                "value": "unknown",
                "satisfied_if": satisfied_if,
                "importance": importance,
                "satisfied": False,
                "contribution": 0,
            }
            continue

        fact_val = c_val.get("value", "unknown")
        if fact_val in ("yes", "no"):
            resolved_count += 1

        satisfied = is_satisfied(fact_val, satisfied_if)

        if satisfied:
            satisfied_weight += importance
            contributions[cid] = {
                "value": fact_val,
                "satisfied_if": satisfied_if,
                "importance": importance,
                "satisfied": True,
                "contribution": importance,
            }
        else:
            contributions[cid] = {
                "value": fact_val,
                "satisfied_if": satisfied_if,
                "importance": importance,
                "satisfied": False,
                "contribution": 0,
            }

    if total_possible_weight > 0:
        criteria_score = (satisfied_weight / total_possible_weight) * 100
    else:
        criteria_score = 0.0

    # Coverage factor: penalise sparse/vague listings
    coverage_ratio = resolved_count / total_count
    # Scale smoothly to 1.0 at 60% coverage, instead of a hard cliff at 40%
    coverage_factor = min(1.0, coverage_ratio / 0.60)

    # 2. Dimensions score
    expected_dims = [
        "trustworthiness",
        "transparency",
        "conditionConfidence",
        "documentationQuality",
        "hiddenRiskSuspicion",
        "marketAboveAverageSignal",
    ]

    dim_scores = []
    for dim_key in expected_dims:
        dim_data = dimensions.get(dim_key)
        raw_score = 3
        if isinstance(dim_data, dict):
            raw_score = dim_data.get("score", 3)
        elif isinstance(dim_data, (int, float)):
            raw_score = dim_data

        try:
            raw_score = int(float(raw_score))
        except (ValueError, TypeError):
            raw_score = 3

        raw_score = max(1, min(5, raw_score))

        if dim_key == "hiddenRiskSuspicion":
            score_for_calc = 6 - raw_score
        else:
            score_for_calc = raw_score

        norm_dim_score = ((score_for_calc - 1) / 4) * 100
        dim_scores.append(norm_dim_score)

    if dim_scores:
        dimensions_score = sum(dim_scores) / len(dim_scores)
    else:
        dimensions_score = 50.0

    raw_blended = (criteria_score * 0.65) + (dimensions_score * 0.35)

    # Apply coverage: blend between 50 (floor for unknown-heavy listings) and raw_blended
    final_score = 50.0 * (1 - coverage_factor) + raw_blended * coverage_factor
    final_score = max(0, min(100, round(final_score)))

    return final_score, criteria_score, dimensions_score, contributions


_IMPORTANCE_PTS = {"high": 3, "medium": 2, "low": 1}
_NEG_PENALTY_PTS = {3: 12, 2: 7, 1: 3}  # per confirmed-present negative criterion
_NEG_RELIEF_PTS = {3: 4, 2: 2, 1: 1}  # per confirmed-absent negative criterion


def calculate_evidence_score(
    normalized_criteria: dict,
    item_config: dict,
    normalized_dimensions: dict,
    model_high_value_unknowns: list,
    model_risk_flags: list,
    normalized_ref_comp: dict,
) -> Tuple[int, float, float, Dict[str, Any]]:
    """Evidence-first scorer for the new split-schema profiles.

    Positive criteria  → additive score (yes only).
    Negative criteria  → penalty when yes (confirmed present), small relief when no.
    High-value unknowns → confidence penalty based on how many remain unresolved.
    Risk flags         → flat penalty per flag reported by the model.
    Dimensions         → 45% weight (same inversion logic for hiddenRiskSuspicion).
    Reference comparison → ±5 modifier.
    Coverage           → floor for listings with mostly unknown answers.
    """
    pos_criteria = item_config.get("explicit_positive_criteria", [])
    neg_criteria = item_config.get("explicit_negative_criteria", [])
    all_criteria = pos_criteria + neg_criteria
    profile_hvunknowns = item_config.get("high_value_unknown_fields", [])

    # 1. Positive score (0-100)
    total_pos_weight = sum(
        _IMPORTANCE_PTS.get(c.get("importance_hint", "medium"), 2) for c in pos_criteria
    )
    earned_pos_weight = sum(
        _IMPORTANCE_PTS.get(c.get("importance_hint", "medium"), 2)
        for c in pos_criteria
        if normalized_criteria.get(c["id"], {}).get("value") == "yes"
    )
    pos_score = (earned_pos_weight / max(total_pos_weight, 1)) * 100

    # 2. Coverage factor (softer curve)
    resolved = sum(
        1
        for c in all_criteria
        if normalized_criteria.get(c["id"], {}).get("value") in ("yes", "no")
    )
    coverage_ratio = resolved / max(len(all_criteria), 1)
    # Instead of a hard cliff at 0.40, we scale smoothly to 1.0 at 60% coverage
    coverage_factor = min(1.0, coverage_ratio / 0.60)

    # 3. Negative penalty: confirmed-present bad things (0-35)
    neg_penalty = min(
        sum(
            _NEG_PENALTY_PTS.get(
                _IMPORTANCE_PTS.get(c.get("importance_hint", "medium"), 2), 7
            )
            for c in neg_criteria
            if normalized_criteria.get(c["id"], {}).get("value") == "yes"
        ),
        35,
    )

    # 4. Negative relief: confirmed-absent bad things (0-15)
    neg_relief = min(
        sum(
            _NEG_RELIEF_PTS.get(
                _IMPORTANCE_PTS.get(c.get("importance_hint", "medium"), 2), 2
            )
            for c in neg_criteria
            if normalized_criteria.get(c["id"], {}).get("value") == "no"
        ),
        15,
    )

    # 5. High-value unknowns (small flat penalty + upside cap)
    n_profile_hvu = len(profile_hvunknowns)
    n_model_hvu = (
        len(model_high_value_unknowns)
        if isinstance(model_high_value_unknowns, list)
        else 0
    )
    hvu_ratio = (n_model_hvu / max(n_profile_hvu, 1)) if n_profile_hvu > 0 else 0
    hvu_penalty = round(hvu_ratio * 2)  # max 2 point flat penalty
    hvu_cap = 100 - round(hvu_ratio * 12)  # caps upside at 88 if all HVUs are missing

    # 6. Risk flags penalty (0-3)
    n_flags = len(model_risk_flags) if isinstance(model_risk_flags, list) else 0
    risk_penalty = min(n_flags, 3)

    # 7. Dimensions score (0-100) — same inversion as blended scorer
    expected_dims = [
        "trustworthiness",
        "transparency",
        "conditionConfidence",
        "documentationQuality",
        "hiddenRiskSuspicion",
        "marketAboveAverageSignal",
    ]
    dim_scores = []
    for dim_key in expected_dims:
        dim_data = normalized_dimensions.get(dim_key, {})
        raw = dim_data.get("score", 3) if isinstance(dim_data, dict) else 3
        try:
            raw = max(1, min(5, int(float(raw))))
        except (ValueError, TypeError):
            raw = 3
        effective = (6 - raw) if dim_key == "hiddenRiskSuspicion" else raw
        dim_scores.append(((effective - 1) / 4) * 100)
    dimensions_score = sum(dim_scores) / max(len(dim_scores), 1)

    # 8. Reference comparison modifier
    closer_to = (
        normalized_ref_comp.get("closer_to", "mixed")
        if isinstance(normalized_ref_comp, dict)
        else "mixed"
    )
    ref_mod = {"good": 4, "bad": 0, "mixed": 0}.get(closer_to, 0)

    # 9. Assemble: 45% positive evidence + 55% dimensions, then apply penalties
    base = 0.45 * pos_score + 0.55 * dimensions_score
    # Neg relief is added before penalties (confirmed safety is real positive signal)
    effective = base + 0.15 * neg_relief
    penalized = effective - neg_penalty - hvu_penalty - risk_penalty + ref_mod

    # Apply HVU upside cap
    penalized = min(penalized, hvu_cap)

    # Coverage floor: sparse listings collapse toward 50 (ordinary) instead of 35
    final = coverage_factor * penalized + (1.0 - coverage_factor) * 50.0
    final = max(0, min(100, round(final)))

    contributions = {
        "_pos_score": pos_score,
        "_dimensions_score": dimensions_score,
        "_neg_relief": neg_relief,
        "_neg_penalty": neg_penalty,
        "_hvu_penalty": hvu_penalty,
        "_risk_penalty": risk_penalty,
        "_ref_mod": ref_mod,
        "_coverage_factor": round(coverage_factor, 2),
    }
    return final, pos_score, dimensions_score, contributions


def calculate_unified_score(
    extracted_facts: dict,
    item_config: dict,
) -> Tuple[int, float, float, Dict[str, Any]]:
    """Calculates unified score for field-type aware schema profiles.

    Supports field types: boolean, number, enum, tier, text.
    Handles field properties: importance, buyer_wants, missing_behavior, polarity.
    """
    field_defs = item_config.get("fields", [])
    dimensions_enabled = item_config.get("dimensions_enabled", True)
    dimensions_weight = float(
        item_config.get("dimensions_weight", 0.35 if dimensions_enabled else 0.0)
    )

    criteria_facts = extracted_facts.get("criteria", {})
    dimensions_facts = extracted_facts.get("dimensions", {})

    total_max_points = 0.0
    earned_points = 0.0
    critical_gaps = 0
    contributions = {}

    for field in field_defs:
        fid = field.get("id")
        ftype = field.get("type", "boolean")
        importance = field.get("importance", "medium")
        pts = _IMPORTANCE_PTS.get(importance, 2)
        total_max_points += pts

        fact_entry = criteria_facts.get(fid, {})
        extracted_val = (
            fact_entry.get("value") if isinstance(fact_entry, dict) else None
        )

        missing_behavior = field.get("missing_behavior", "neutral")
        polarity = field.get("polarity", "positive")
        buyer_wants = field.get("buyer_wants", {})

        field_earned = 0.0
        status = "neutral"

        if extracted_val is None or extracted_val == "unknown":
            if missing_behavior == "critical_gap":
                critical_gaps += 1
                status = "missing_critical"
            elif missing_behavior == "penalize":
                field_earned = -0.5 * pts
                status = "penalized_missing"
            else:
                status = "missing"
        else:
            if ftype == "boolean":
                is_yes = str(extracted_val).lower() in ("yes", "y", "true", "1")
                is_no = str(extracted_val).lower() in ("no", "n", "false", "0")
                target_match = buyer_wants.get(
                    "match", True if polarity != "negative" else False
                )

                if (is_yes and target_match is True) or (
                    is_no and target_match is False
                ):
                    field_earned = pts
                    status = "satisfied"
                elif (is_yes and target_match is False) or (
                    is_no and target_match is True
                ):
                    field_earned = 0.0 if polarity != "negative" else -1.0 * pts
                    status = "violated"

            elif ftype == "number":
                try:
                    num_val = float(extracted_val)
                    req_min = buyer_wants.get("min")
                    req_max = buyer_wants.get("max")
                    is_ok = True
                    if req_min is not None and num_val < float(req_min):
                        is_ok = False
                    if req_max is not None and num_val > float(req_max):
                        is_ok = False

                    if is_ok:
                        field_earned = pts
                        status = "satisfied"
                    else:
                        field_earned = 0.0
                        status = "violated"
                except (ValueError, TypeError):
                    status = "invalid_number"

            elif ftype == "enum":
                preferred = buyer_wants.get("preferred", [])
                excluded = buyer_wants.get("excluded", [])
                val_str = str(extracted_val).strip()

                if val_str in preferred:
                    field_earned = pts
                    status = "satisfied"
                elif val_str in excluded:
                    field_earned = -0.5 * pts
                    status = "violated"
                else:
                    field_earned = 0.5 * pts
                    status = "partial"

            elif ftype == "tier":
                try:
                    tier_val = float(extracted_val)
                    min_tier = float(buyer_wants.get("min", 5))
                    if tier_val >= min_tier:
                        field_earned = pts
                        status = "satisfied"
                    else:
                        ratio = max(0.0, tier_val / min_tier)
                        field_earned = pts * ratio
                        status = "partial"
                except (ValueError, TypeError):
                    status = "invalid_tier"

            elif ftype == "text":
                if buyer_wants.get("present", True):
                    field_earned = pts if extracted_val else 0.0
                    status = "satisfied" if extracted_val else "missing"

        earned_points += field_earned
        contributions[fid] = {
            "value": extracted_val,
            "earned": field_earned,
            "max": pts,
            "status": status,
            # A hard constraint is a legal or physical limit, not a preference:
            # an A2 licence holder cannot buy a 90 kW motorcycle at any score,
            # and a 200 cm sideboard does not fit a 180 cm alcove. Recorded here
            # so score_listing can disqualify rather than merely deduct.
            "hard": bool(field.get("hard")),
        }

    raw_field_score = (max(0.0, earned_points) / max(total_max_points, 1.0)) * 100.0

    # Handle dimensions if enabled
    dimensions_score = 50.0
    if dimensions_enabled:
        expected_dims = [
            "trustworthiness",
            "transparency",
            "conditionConfidence",
            "documentationQuality",
            "hiddenRiskSuspicion",
            "marketAboveAverageSignal",
        ]
        dim_scores = []
        for dim_key in expected_dims:
            dim_data = dimensions_facts.get(dim_key, {})
            raw = dim_data.get("score", 3) if isinstance(dim_data, dict) else 3
            try:
                raw = max(1, min(5, int(float(raw))))
            except (ValueError, TypeError):
                raw = 3
            effective = (6 - raw) if dim_key == "hiddenRiskSuspicion" else raw
            dim_scores.append(((effective - 1) / 4) * 100)
        dimensions_score = sum(dim_scores) / max(len(dim_scores), 1)

    field_weight = 1.0 - dimensions_weight
    blended = (raw_field_score * field_weight) + (dimensions_score * dimensions_weight)

    # Penalize critical gaps
    if critical_gaps > 0:
        blended = blended * (0.8**critical_gaps)

    final_score = max(0, min(100, round(blended)))
    return final_score, raw_field_score, dimensions_score, contributions


def score_listing(extracted_facts: dict, item_config: dict) -> ScoringResult:
    """Unified entry point to score a listing based on extracted facts and campaign profile.

    This function automatically routes between legacy blended scoring, evidence-first scoring,
    and the unified field-type aware scoring.
    """
    has_unified_fields = bool(item_config.get("fields"))
    is_new_schema = bool(
        item_config.get("explicit_positive_criteria")
        or item_config.get("explicit_negative_criteria")
    )

    if has_unified_fields:
        (
            score,
            criteria_score,
            dimensions_score,
            contributions,
        ) = calculate_unified_score(extracted_facts, item_config)
    elif is_new_schema:
        criteria = extracted_facts.get("criteria", {})
        dimensions = extracted_facts.get("dimensions", {})
        ref_comp = extracted_facts.get("reference_comparison", {})
        hvu = extracted_facts.get("high_value_unknowns", [])
        risk_flags = extracted_facts.get("risk_flags", [])

        (
            score,
            criteria_score,
            dimensions_score,
            contributions,
        ) = calculate_evidence_score(
            criteria, item_config, dimensions, hvu, risk_flags, ref_comp
        )
    else:
        # Legacy blended scoring
        # In legacy mode, extracted_facts might be the criteria dictionary itself
        # or a nested dictionary containing 'criteria'
        criteria = (
            extracted_facts.get("criteria")
            if isinstance(extracted_facts, dict) and "criteria" in extracted_facts
            else extracted_facts
        )
        if not isinstance(criteria, dict):
            criteria = {}
        dimensions = (
            extracted_facts.get("dimensions", {})
            if isinstance(extracted_facts, dict)
            else {}
        )
        scoring_model = item_config.get("scoring_model", {})
        weights = scoring_model.get("weights", {})

        (
            score,
            criteria_score,
            dimensions_score,
            contributions,
        ) = calculate_blended_score(criteria, weights, dimensions)

    disqualified_by, unverified = evaluate_hard_constraints(contributions)
    if disqualified_by:
        # Ranking a disqualified listing at all would put an unbuyable item in
        # front of a buyer, so the score collapses rather than being reduced.
        logger.info(
            "Listing disqualified by hard constraint(s): %s", ", ".join(disqualified_by)
        )
        score = 0

    return ScoringResult(
        score=score,
        criteria_score=criteria_score,
        dimensions_score=dimensions_score,
        contributions=contributions,
        is_new_schema=is_new_schema or has_unified_fields,
        disqualified_by=disqualified_by,
        unverified_constraints=unverified,
    )
