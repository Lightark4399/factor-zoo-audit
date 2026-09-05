"""Card acceptance properties, independent of the ten current YAML filenames."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
import yaml

from fza.factors.registry import (
    VALID_REFERENCE_ROLES,
    CardError,
    HypothesisCard,
    load_all,
)


def _resource(data):
    return SimpleNamespace(
        name="generated-card.yaml", read_text=lambda **kwargs: yaml.safe_dump(data)
    )


@pytest.mark.parametrize("role", sorted(VALID_REFERENCE_ROLES))
@pytest.mark.parametrize("locator", [None, "", "   "])
def test_every_verified_reference_needs_a_nonblank_locator(role, locator):
    # A valid first origin must not vouch for a later invalid reference. This
    # covers every supported role, including another definition origin.
    data = deepcopy(load_all()["bm_ratio"].card.raw)
    data["references"].append(
        {
            "citation": "Synthetic reference for boundary validation",
            "role": role,
            "locator": locator,
            "verification": "VERIFIED",
        }
    )
    with pytest.raises(CardError, match="locator"):
        HypothesisCard.from_yaml(_resource(data))


def test_an_unverified_origin_without_locator_remains_pending():
    data = deepcopy(load_all()["log_mktcap"].card.raw)
    # A missing locator is allowed for an honestly unverified relation.
    card = HypothesisCard.from_yaml(_resource(data))
    assert card.lineage_status == "UNVERIFIED"
    assert card.published_anomaly_eligibility["status"] == "PENDING"
