"""Phase 0 smoke tests: config.yaml loads and validates, plus overlay merging."""

import pytest

from jobpilot.config import get_config, merge_sources


def test_config_loads():
    cfg = get_config()
    assert cfg.crawl.jobs_per_site == 10
    assert cfg.app.edit_max_rounds >= 1


def test_at_least_one_source_defined():
    cfg = get_config()
    assert len(cfg.sources) >= 1
    keys = {s.key for s in cfg.sources}
    assert {"itviec", "topcv", "vietnamworks"} <= keys


def test_overlay_keeps_sources_it_has_never_heard_of():
    """The Settings page writes the source list as it stood when you saved it.
    Overwriting with that list makes every source added since disappear — not
    default-off but *absent*, so the Settings page cannot even offer it. This is
    what hid the tier-2 feeds on any machine that had opened Settings once."""
    base = [
        {"key": "itviec", "tier": 1, "enabled": True},
        {"key": "weworkremotely", "tier": 2, "enabled": True},
    ]
    overlay = [{"key": "itviec", "tier": 1, "enabled": False}]  # saved before tier 2 existed

    merged = merge_sources(base, overlay)
    assert [s["key"] for s in merged] == ["itviec", "weworkremotely"]
    assert merged[0]["enabled"] is False  # your preference still wins
    assert merged[1]["enabled"] is True  # the new source survives


def test_overlay_may_still_add_a_source_of_its_own():
    merged = merge_sources([{"key": "itviec", "enabled": True}], [{"key": "mine", "enabled": True}])
    assert [s["key"] for s in merged] == ["itviec", "mine"]


def test_merge_sources_ignores_junk_entries():
    merged = merge_sources([{"key": "itviec"}], ["nonsense", {"no_key": 1}])
    assert [s["key"] for s in merged] == ["itviec"]


def test_enabled_sources_subset():
    cfg = get_config()
    for s in cfg.enabled_sources():
        assert s.enabled is True


# --------------------------------------------------------------------------- #
# The API token guard (jobpilot/api/security.py)
# --------------------------------------------------------------------------- #
def test_a_placeholder_token_refuses_to_start():
    from jobpilot.api.security import check_api_token

    for bad in ("changeme", "CHANGEME", "", "secret"):
        with pytest.raises(RuntimeError, match="refusing to start"):
            check_api_token(bad)


def test_a_short_token_refuses_to_start():
    """Below 20 characters a token is also below redact.py's 12-character floor
    territory and too small to be worth guessing at leisure."""
    from jobpilot.api.security import check_api_token

    with pytest.raises(RuntimeError, match="characters"):
        check_api_token("a1b2c3d4")


def test_the_error_hands_back_a_usable_replacement():
    """A guard that only says no gets worked around; one that prints the fix
    gets followed."""
    from jobpilot.api.security import MIN_API_TOKEN_LEN, check_api_token

    with pytest.raises(RuntimeError) as exc:
        check_api_token("changeme")
    suggested = str(exc.value).split("JOBPILOT_API_TOKEN=")[-1].strip()
    assert len(suggested) >= MIN_API_TOKEN_LEN


def test_a_generated_token_passes_its_own_guard():
    from jobpilot.api.security import check_api_token, generate_token

    check_api_token(generate_token())  # must not raise


def test_token_comparison_is_constant_time_and_total():
    from jobpilot.api.security import token_matches

    assert token_matches("abc", "abc")
    assert not token_matches("abc", "abd")
    # A missing expected value must never authenticate an empty request.
    assert not token_matches(None, None)
    assert not token_matches("", "")
    assert not token_matches("abc", None)
