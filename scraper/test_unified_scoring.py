import pytest
from scoring import calculate_unified_score, score_listing


def test_unified_scoring_boolean_fields():
    item_config = {
        "fields": [
            {
                "id": "accidentFree",
                "label": "Accident Free",
                "type": "boolean",
                "importance": "high",
                "buyer_wants": {"match": True},
                "polarity": "positive",
            },
            {
                "id": "damageReported",
                "label": "Damage Reported",
                "type": "boolean",
                "importance": "high",
                "buyer_wants": {"match": False},
                "polarity": "negative",
            },
        ],
        "dimensions_enabled": False,
    }

    extracted_facts = {
        "criteria": {
            "accidentFree": {"value": "yes"},
            "damageReported": {"value": "no"},
        }
    }

    res = score_listing(extracted_facts, item_config)
    assert res.score == 100
    assert res.is_new_schema is True


def test_unified_scoring_numeric_and_enum_fields():
    item_config = {
        "fields": [
            {
                "id": "ramGb",
                "type": "number",
                "importance": "high",
                "buyer_wants": {"min": 16},
            },
            {
                "id": "screenType",
                "type": "enum",
                "importance": "medium",
                "buyer_wants": {"preferred": ["OLED", "IPS"]},
            },
        ],
        "dimensions_enabled": False,
    }

    extracted_facts = {
        "criteria": {
            "ramGb": {"value": 16},
            "screenType": {"value": "OLED"},
        }
    }

    res = score_listing(extracted_facts, item_config)
    assert res.score == 100


def test_unified_scoring_critical_gap_penalty():
    item_config = {
        "fields": [
            {
                "id": "cpuModel",
                "type": "text",
                "importance": "high",
                "missing_behavior": "critical_gap",
                "buyer_wants": {"present": True},
            },
        ],
        "dimensions_enabled": False,
    }

    extracted_facts = {
        "criteria": {
            "cpuModel": {"value": None},
        }
    }

    score, field_score, dim_score, contribs = calculate_unified_score(
        extracted_facts, item_config
    )
    assert contribs["cpuModel"]["status"] == "missing_critical"
    # 0 score scaled down by 0.8 critical gap penalty
    assert score == 0


def _single_field_config(field, **overrides):
    """Builds a one-field profile with dimensions off, so the score is the field score."""
    config = {"fields": [field], "dimensions_enabled": False}
    config.update(overrides)
    return config


def test_tier_field_scores_proportionally_below_target():
    item_config = _single_field_config(
        {
            "id": "conditionTier",
            "type": "tier",
            "importance": "high",
            "buyer_wants": {"min": 5},
        }
    )

    _, _, _, contribs = calculate_unified_score(
        {"criteria": {"conditionTier": {"value": 3}}}, item_config
    )
    # 3 of a required 5 earns 60% of the field's 3 points.
    assert contribs["conditionTier"]["status"] == "partial"
    assert contribs["conditionTier"]["earned"] == pytest.approx(1.8)


def test_tier_field_at_or_above_target_is_fully_satisfied():
    item_config = _single_field_config(
        {
            "id": "conditionTier",
            "type": "tier",
            "importance": "high",
            "buyer_wants": {"min": 4},
        }
    )

    score, _, _, contribs = calculate_unified_score(
        {"criteria": {"conditionTier": {"value": 5}}}, item_config
    )
    assert contribs["conditionTier"]["status"] == "satisfied"
    assert score == 100


def test_negative_polarity_boolean_is_penalised_when_violated():
    item_config = _single_field_config(
        {
            "id": "damageReported",
            "type": "boolean",
            "importance": "high",
            "buyer_wants": {"match": False},
            "polarity": "negative",
        }
    )

    score, _, _, contribs = calculate_unified_score(
        {"criteria": {"damageReported": {"value": "yes"}}}, item_config
    )
    assert contribs["damageReported"]["status"] == "violated"
    # Negative polarity subtracts the field's full weight rather than merely
    # withholding it; the total is floored at zero.
    assert contribs["damageReported"]["earned"] == pytest.approx(-3.0)
    assert score == 0


def test_enum_excluded_value_is_penalised_and_unknown_value_is_partial():
    item_config = _single_field_config(
        {
            "id": "screenType",
            "type": "enum",
            "importance": "medium",
            "buyer_wants": {"preferred": ["OLED"], "excluded": ["TN"]},
        }
    )

    _, _, _, excluded = calculate_unified_score(
        {"criteria": {"screenType": {"value": "TN"}}}, item_config
    )
    assert excluded["screenType"]["status"] == "violated"
    assert excluded["screenType"]["earned"] == pytest.approx(-1.0)

    # A value that is neither preferred nor excluded lands in the middle.
    _, _, _, other = calculate_unified_score(
        {"criteria": {"screenType": {"value": "IPS"}}}, item_config
    )
    assert other["screenType"]["status"] == "partial"
    assert other["screenType"]["earned"] == pytest.approx(1.0)


def test_number_outside_requested_range_is_violated():
    item_config = _single_field_config(
        {
            "id": "ramGb",
            "type": "number",
            "importance": "high",
            "buyer_wants": {"min": 16, "max": 64},
        }
    )

    for value in (8, 128):
        _, _, _, contribs = calculate_unified_score(
            {"criteria": {"ramGb": {"value": value}}}, item_config
        )
        assert contribs["ramGb"]["status"] == "violated", value
        assert contribs["ramGb"]["earned"] == 0.0


def test_non_numeric_value_is_flagged_rather_than_crashing():
    item_config = _single_field_config(
        {
            "id": "ramGb",
            "type": "number",
            "importance": "high",
            "buyer_wants": {"min": 16},
        }
    )

    _, _, _, contribs = calculate_unified_score(
        {"criteria": {"ramGb": {"value": "sixteen"}}}, item_config
    )
    assert contribs["ramGb"]["status"] == "invalid_number"
    assert contribs["ramGb"]["earned"] == 0.0


def test_penalize_missing_behavior_subtracts_half_the_field_weight():
    item_config = _single_field_config(
        {
            "id": "serviceHistory",
            "type": "text",
            "importance": "medium",
            "missing_behavior": "penalize",
            "buyer_wants": {"present": True},
        }
    )

    _, _, _, contribs = calculate_unified_score(
        {"criteria": {"serviceHistory": {"value": None}}}, item_config
    )
    assert contribs["serviceHistory"]["status"] == "penalized_missing"
    assert contribs["serviceHistory"]["earned"] == pytest.approx(-1.0)


def test_absent_field_defaults_to_neutral_missing():
    item_config = _single_field_config(
        {
            "id": "serviceHistory",
            "type": "text",
            "importance": "medium",
            "buyer_wants": {"present": True},
        }
    )

    # The criterion is absent from the extraction entirely, not merely null.
    _, _, _, contribs = calculate_unified_score({"criteria": {}}, item_config)
    assert contribs["serviceHistory"]["status"] == "missing"
    assert contribs["serviceHistory"]["earned"] == 0.0


def test_dimensions_are_blended_in_at_the_configured_weight():
    item_config = {
        "fields": [
            {
                "id": "accidentFree",
                "type": "boolean",
                "importance": "high",
                "buyer_wants": {"match": True},
            }
        ],
        "dimensions_enabled": True,
        "dimensions_weight": 0.5,
    }

    # Dimensions are omitted, so each defaults to a neutral 3 of 5 => 50.
    score, field_score, dim_score, _ = calculate_unified_score(
        {"criteria": {"accidentFree": {"value": "yes"}}}, item_config
    )
    assert field_score == pytest.approx(100.0)
    assert dim_score == pytest.approx(50.0)
    assert score == 75


def test_hidden_risk_dimension_is_inverted():
    item_config = {"fields": [], "dimensions_enabled": True, "dimensions_weight": 1.0}

    facts = {
        "dimensions": {
            key: {"score": 5}
            for key in (
                "trustworthiness",
                "transparency",
                "conditionConfidence",
                "documentationQuality",
                "hiddenRiskSuspicion",
                "marketAboveAverageSignal",
            )
        }
    }

    _, _, dim_score, _ = calculate_unified_score(facts, item_config)
    # Five dimensions score 100; a maximal hiddenRiskSuspicion inverts to 0.
    assert dim_score == pytest.approx(500.0 / 6.0)


def test_profile_without_fields_still_uses_the_legacy_path():
    item_config = {
        "extraction_criteria": [{"id": "unfallfrei", "type": "boolean"}],
        "scoring_model": {"weights": {"unfallfrei": {"satisfied_if": True}}},
    }

    res = score_listing({"criteria": {"unfallfrei": {"value": "yes"}}}, item_config)
    assert res.is_new_schema is False
    assert 0 <= res.score <= 100
