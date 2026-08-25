"""Tests for the factor library.

Two things are checked for every factor, and one for the library as a whole.

Per factor: it produces values on the fixture, and its reads respect the as-of
contract. Neither says the factor is any good -- fixture prices are a random walk
-- but both would catch the failures that have actually occurred here: a window
expressed in the wrong unit, a tag the fixture does not carry, a read that
bypassed the view.

For the library: every registered factor has a card whose falsification criteria
are non-empty, and every category the SPEC promises is represented. A factor
library is only comparable across rows if every row went through the same
protocol, and the registry is what makes that structural rather than aspirational.
"""

from __future__ import annotations

import pandas as pd
import pytest

from fza.factors.registry import VALID_CATEGORIES, all_factors, load_all, summary_table
from fza.fixtures import load_fixture_into
from fza.pipeline.run import compute_factor
from fza.store import Store

SIGNAL_DATES = pd.DatetimeIndex(pd.date_range("2019-06-30", "2021-12-31", freq="ME"))


@pytest.fixture(scope="module")
def store():
    s = Store()
    load_fixture_into(s)
    yield s
    s.close()


@pytest.fixture(scope="module")
def factors():
    return load_all()


def _factor_ids():
    load_all()
    return sorted(all_factors())


# ----------------------------------------------------------------------
# Every factor, individually
# ----------------------------------------------------------------------
@pytest.mark.parametrize("factor_id", _factor_ids())
def test_factor_produces_values(factor_id, store, factors):
    """An empty factor is always a bug, and the pipeline refuses to pass one on.

    This has caught two real defects: a momentum window expressed in rows of a
    resampled frame while meaning trading days, and three factors reading tags
    the fixture did not carry.
    """
    run = compute_factor(factors[factor_id], store, SIGNAL_DATES)
    assert len(run.values) > 0
    assert len(run.panel) > 0
    assert run.protocol.n_dates > 0


@pytest.mark.parametrize("factor_id", _factor_ids())
def test_factor_respects_the_asof_contract(factor_id, store, factors):
    """No read may return a filing dated after the day it was asked for."""
    run = compute_factor(factors[factor_id], store, SIGNAL_DATES)
    assert run.read_path_check["ok"], run.read_path_check.get("sample")


@pytest.mark.parametrize("factor_id", _factor_ids())
def test_factor_values_are_finite(factor_id, store, factors):
    """Infinities from a zero denominator would survive standardisation as NaN
    and quietly shrink the cross-section instead of raising."""
    run = compute_factor(factors[factor_id], store, SIGNAL_DATES)
    import numpy as np

    assert np.isfinite(run.values["value"]).all()


# ----------------------------------------------------------------------
# The library as a whole
# ----------------------------------------------------------------------
def test_every_factor_has_falsification_criteria(factors):
    """A card with no stated way to fail cannot be tested against."""
    for factor_id, factor in factors.items():
        assert factor.card.falsification, f"{factor_id} has no falsification criteria"
        assert len(factor.card.falsification) >= 2


def test_every_factor_has_a_reference(factors):
    """These are reimplementations of published definitions, and a reader who
    doubts a result has to be able to find the paper."""
    for factor_id, factor in factors.items():
        assert factor.card.references, f"{factor_id} cites nothing"


def test_categories_are_valid_and_broad(factors):
    """The SPEC promises coverage across categories, not depth in one."""
    categories = {f.category for f in factors.values()}
    assert categories <= VALID_CATEGORIES
    assert len(categories) >= 6, f"only {len(categories)} categories represented"


def test_fundamental_factors_declare_their_tags(factors):
    """A factor that reads a tag it did not declare escapes the trap
    measurement, which is scoped by the declaration."""
    for factor_id, factor in factors.items():
        if factor.filing_lag_days > 0:
            assert factor.tags, f"{factor_id} declares a lag but no tags"


def test_summary_table_covers_every_registered_factor(factors):
    table = summary_table()
    assert len(table) == len(factors)
    assert set(table["factor_id"]) == set(factors)


def test_sign_convention_is_documented_for_inverted_factors(factors):
    """Size, volatility, turnover and asset growth are negated so that a
    positive IC means the factor predicts returns. The card has to say so, or a
    reader will interpret the sign as a finding."""
    for factor_id in ("log_mktcap", "idio_vol", "turnover", "asset_growth"):
        card = factors[factor_id].card
        text = (card.definition + card.economic_rationale).lower()
        assert "negat" in text or "invert" in text or "long side" in text
