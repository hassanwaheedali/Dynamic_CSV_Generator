"""Section 3 -- brand lookup behaviour.

Invariants are discovered from ``VENDOR_REGISTRY`` (every store x platform brand table), so a
new brand or store is covered the day it is configured.  A handful of fixed adversarial spellings
stay literal because they are real sheet inputs, not table lookups.
"""

from __future__ import annotations

import pytest

from brands import (
    BRANDS_ALFA,
    BRANDS_DIGI,
    canonical_brand_key,
    resolve_brand,
)
from vendor_config import VENDOR_REGISTRY, resolve_cell

CELLS = [(key, platform) for key in VENDOR_REGISTRY for platform in ("digi", "alfa")]


def test_legacy_lists_are_well_formed() -> None:
    for table in (BRANDS_DIGI, BRANDS_ALFA):
        assert len(table) > 0
        assert all(isinstance(v, int) and v > 0 for v in table.values())
        assert all(k == k.strip().lower() and k for k in table)


@pytest.mark.parametrize("vendor_key", list(VENDOR_REGISTRY))
def test_every_configured_brand_resolves_to_its_own_id_on_its_own_platform(vendor_key: str) -> None:
    """Round trip over the whole table: key -> resolver -> the id configured for that key."""
    cfg = VENDOR_REGISTRY[vendor_key]
    checked = 0
    for platform, attr in (("digi", "digi_id"), ("alfa", "alfa_id")):
        for brand_key, brand_id in resolve_cell(cfg, platform).brands.items():
            res = resolve_brand(brand_key, vendor_cfg=cfg)
            assert getattr(res, attr) == brand_id, (vendor_key, platform, brand_key)
            checked += 1
    assert checked > 0, f"{vendor_key} configures no brands at all; the round trip proved nothing"


@pytest.mark.parametrize("vendor_key", list(VENDOR_REGISTRY))
def test_a_brand_never_resolves_on_a_platform_that_does_not_list_it(vendor_key: str) -> None:
    """Isolation: an id absent from one cell's table must come back None, not borrowed."""
    cfg = VENDOR_REGISTRY[vendor_key]
    digi, alfa = resolve_cell(cfg, "digi").brands, resolve_cell(cfg, "alfa").brands
    for brand_key in set(digi) | set(alfa):
        res = resolve_brand(brand_key, vendor_cfg=cfg)
        if res.normalized not in digi:
            assert res.digi_id is None, (vendor_key, "digi", brand_key)
        if res.normalized not in alfa:
            assert res.alfa_id is None, (vendor_key, "alfa", brand_key)


@pytest.mark.parametrize("vendor_key", list(VENDOR_REGISTRY))
def test_case_and_whitespace_never_change_the_answer(vendor_key: str) -> None:
    cfg = VENDOR_REGISTRY[vendor_key]
    names = set(resolve_cell(cfg, "digi").brands) | set(resolve_cell(cfg, "alfa").brands)
    assert names
    for name in names:
        base = resolve_brand(name, vendor_cfg=cfg)
        for spelling in (name.upper(), f"  {name.title()}  ", name.title()):
            got = resolve_brand(spelling, vendor_cfg=cfg)
            assert (got.digi_id, got.alfa_id) == (base.digi_id, base.alfa_id), (vendor_key, spelling)


@pytest.mark.parametrize("vendor_key", list(VENDOR_REGISTRY))
def test_no_fuzzy_matching_ever(vendor_key: str) -> None:
    """A near-miss built from every real brand (typo, suffix, prefix) must not resolve.

    ("Dawlanc" is deliberately excluded: it lives in the explicit alias table.)
    """
    cfg = VENDOR_REGISTRY[vendor_key]
    names = set(resolve_cell(cfg, "digi").brands) | set(resolve_cell(cfg, "alfa").brands)
    known = names | {canonical_brand_key(n, cfg.brand_aliases) for n in names}
    for name in names:
        for near_miss in (f"{name}x", f"{name} Pakistan Ltd", f"x{name}"):
            if near_miss.strip().lower() in known:
                continue
            res = resolve_brand(near_miss, vendor_cfg=cfg)
            assert res.digi_id is None and res.alfa_id is None, (vendor_key, near_miss)


def test_fixed_adversarial_spellings_from_the_real_sheet() -> None:
    """Literal regressions: these are alias-table facts, so they are pinned rather than derived."""
    assert canonical_brand_key("Superasia") == "super asia"  # 45 real rows omit the space
    assert canonical_brand_key("xiaomi") == "xioami"  # Alfa's own spelling
    assert canonical_brand_key("Something New") == "something new"  # unknown stays itself
    assert resolve_brand("Superasia").normalized == "super asia"
    for near_miss in ("Dawlance Pak", "Haierr", "TCL Pakistan Ltd", "Greee"):
        res = resolve_brand(near_miss)
        assert res.digi_id is None and res.alfa_id is None, near_miss


@pytest.mark.parametrize("vendor_key", list(VENDOR_REGISTRY))
def test_every_configured_alias_normalizes_and_resolves_independently(vendor_key: str) -> None:
    cfg = VENDOR_REGISTRY[vendor_key]
    for spelling, target in cfg.brand_aliases.items():
        result = resolve_brand(spelling, vendor_cfg=cfg)
        assert result.normalized == target, (vendor_key, spelling)
        for platform, attr in (("digi", "digi_id"), ("alfa", "alfa_id")):
            table = resolve_cell(cfg, platform).brands
            expected = table.get(target)
            assert getattr(result, attr) == expected, (vendor_key, platform, spelling)
