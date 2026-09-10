import identity
import playbooks


def facts(**values):
    return {"criteria": {k: {"value": v} for k, v in values.items()}}


CARS = playbooks.get_playbook("vehicles/cars")
LAPTOPS = playbooks.get_playbook("electronics/laptops")
BIKES = playbooks.get_playbook("vehicles/motorcycles")


def test_full_car_identity_resolves_to_the_dossier_key():
    key, parts = identity.resolve(
        facts(make="BMW", model="320d Touring", generationCode="E90", engineCode="N47"),
        CARS,
    )

    assert key == "bmw/320d-touring/e90/n47"
    assert identity.display_name(parts) == "bmw 320d touring e90 n47"


def test_seller_decoration_is_stripped_from_the_key():
    """Two listings for the same car must not get different dossiers."""
    plain, _ = identity.resolve(facts(make="BMW", model="320d"), CARS)
    shouty, _ = identity.resolve(facts(make="BMW", model="320d TOP ZUSTAND !!!"), CARS)

    assert plain == shouty == "bmw/320d"


def test_missing_optional_parts_yield_a_coarser_but_valid_key():
    key, _ = identity.resolve(facts(make="VW", model="Golf VII"), CARS)
    assert key == "vw/golf-vii"


def test_missing_required_field_refuses_to_resolve():
    """Under-resolving costs a lookup; mis-resolving mis-scores with confidence."""
    key, reason = identity.resolve(facts(model="320d", engineCode="N47"), CARS)

    assert key is None
    assert "make" in reason


def test_unknown_placeholder_counts_as_missing():
    key, reason = identity.resolve(facts(make="unknown", model="320d"), CARS)
    assert key is None
    assert "make" in reason


def test_empty_facts_do_not_resolve():
    key, reason = identity.resolve({"criteria": {}}, CARS)
    assert key is None
    assert reason


def test_laptop_identity_uses_brand_and_model():
    key, _ = identity.resolve(
        facts(brand="Apple", modelName='MacBook Pro 15" 2019'), LAPTOPS
    )
    assert key == "apple/macbook-pro-15-2019"


def test_motorcycle_identity_resolves():
    key, _ = identity.resolve(facts(make="Yamaha", model="MT-07"), BIKES)
    assert key == "yamaha/mt-07"


def test_category_without_identity_fields_is_reported_not_guessed():
    fake = {"key": "furniture/sofas", "fields": []}
    key, reason = identity.resolve(facts(brand="Ikea"), fake)

    assert key is None
    assert "no identity fields" in reason


def test_normalisation_is_idempotent():
    once = identity.normalize_part("BMW 320d Touring")
    twice = identity.normalize_part(once)
    assert once == twice == "bmw-320d-touring"


def test_plain_values_are_read_as_well_as_wrapped_ones():
    """Extraction wraps values in dicts; hand-built facts may not."""
    raw = {"criteria": {"make": "BMW", "model": "320d"}}
    key, _ = identity.resolve(raw, CARS)
    assert key == "bmw/320d"


def test_resolve_or_log_returns_none_pair_when_unresolved():
    key, parts = identity.resolve_or_log({"criteria": {}}, CARS, listing_id="x")
    assert key is None and parts is None
