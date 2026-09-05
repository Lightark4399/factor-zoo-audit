"""Factor registry: a factor cannot exist without a hypothesis card.

Registration requires the card, and the card requires an economic mechanism, a
precise definition including timing, and falsification criteria. That is
enforced here rather than asked for in a style guide, because acceptance
criterion 4 in ``SPEC.md`` is otherwise a promise the repository has no way to
keep.

The card is not documentation. Two of its fields do real work:

``economic_rationale``
    Why this should predict returns at all. A factor without one is a data-mined
    pattern, and the difference between the two is the difference between
    research and search. It is also the thing BlackRock's job description asks
    for in so many words: *why an alpha idea should work, what economic or
    behavioural mechanism supports it, and under what conditions it persists.*

``falsification``
    What result would make you abandon it. Written before the factor is run, and
    checked in the report afterwards. A criterion that is never tested is
    decoration; the test suite asserts that every card's criteria appear in the
    factor's report.

Why a plugin registry rather than a module of functions
--------------------------------------------------------
Adding a factor must not require touching framework code. That is partly
hygiene, and partly the physical boundary for AI-assisted work: ``factors/`` is
writable, the audit and universe machinery is not. A registry makes that boundary
enforceable by directory rather than by discipline.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path

import pandas as pd
import yaml

CARDS_DIR = files("fza.factors").joinpath("cards")
DENOMINATORS_FILE = files("fza.factors").joinpath("denominators.yaml")

REQUIRED_CARD_FIELDS = (
    "factor_id",
    "name",
    "category",
    "economic_rationale",
    "persistence_conditions",
    "definition",
    "timing",
    "falsification",
    "references",
    "published_anomaly_eligibility",
)

VALID_REFERENCE_ROLES = {
    "definition_origin",
    "mechanism",
    "robustness",
    "competing_explanation",
    "comparator",
}
VALID_REFERENCE_VERIFICATION = {"VERIFIED", "UNVERIFIED"}
VALID_DENOMINATOR_STATUSES = {"INCLUDED", "EXCLUDED", "PENDING"}

VALID_CATEGORIES = {
    "value",
    "momentum",
    "reversal",
    "size",
    "profitability",
    "investment",
    "risk",
    "liquidity",
    "network",  # audited separately: see SPEC on the method-audit section
}


class CardError(ValueError):
    """Raised when a hypothesis card is missing or malformed."""


@dataclass(frozen=True)
class HypothesisCard:
    """The claim a factor makes, written before it is implemented."""

    factor_id: str
    name: str
    category: str
    economic_rationale: str
    persistence_conditions: str
    definition: str
    timing: dict
    falsification: list[str]
    references: list[dict]
    published_anomaly_eligibility: dict
    raw: dict = field(default_factory=dict)

    @property
    def lineage_status(self) -> str:
        origins = [
            reference
            for reference in self.references
            if reference["role"] == "definition_origin"
        ]
        if not origins:
            return "UNSUPPORTED_LINEAGE"
        if not any(reference["verification"] == "VERIFIED" for reference in origins):
            return "UNVERIFIED"
        if self.raw.get("documented_variants"):
            return "DOCUMENTED_VARIANT"
        return "EXACT_REPLICATION"

    @classmethod
    def from_yaml(cls, path) -> HypothesisCard:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        missing = [f for f in REQUIRED_CARD_FIELDS if f not in data or data[f] in (None, "")]
        if missing:
            raise CardError(f"{path.name}: missing or empty field(s): {missing}")

        if data["category"] not in VALID_CATEGORIES:
            raise CardError(
                f"{path.name}: category {data['category']!r} not in {sorted(VALID_CATEGORIES)}"
            )

        timing = data["timing"]
        for key in ("signal_computed", "earliest_execution", "execution_price"):
            if key not in timing:
                raise CardError(f"{path.name}: timing.{key} is required")

        falsification = data["falsification"]
        if not isinstance(falsification, list) or not falsification:
            raise CardError(
                f"{path.name}: falsification must be a non-empty list. A factor "
                "with no stated way to fail cannot be tested."
            )

        references = data["references"]
        if not isinstance(references, list) or not references:
            raise CardError(f"{path.name}: references must be a non-empty list")
        for index, reference in enumerate(references):
            if not isinstance(reference, dict):
                raise CardError(
                    f"{path.name}: references[{index}] must be structured, not a string"
                )
            missing_reference = [
                key
                for key in ("citation", "role", "locator", "verification")
                if key not in reference
            ]
            if missing_reference:
                raise CardError(
                    f"{path.name}: references[{index}] missing {missing_reference}"
                )
            if reference["role"] not in VALID_REFERENCE_ROLES:
                raise CardError(
                    f"{path.name}: references[{index}].role must be one of "
                    f"{sorted(VALID_REFERENCE_ROLES)}"
                )
            if reference["verification"] not in VALID_REFERENCE_VERIFICATION:
                raise CardError(
                    f"{path.name}: references[{index}].verification must be "
                    f"VERIFIED or UNVERIFIED"
                )
            locator = reference["locator"]
            if reference["verification"] == "VERIFIED" and (
                not isinstance(locator, str) or not locator.strip()
            ):
                raise CardError(
                    f"{path.name}: references[{index}].locator must be a nonblank "
                    "string for a VERIFIED reference"
                )

        eligibility = data["published_anomaly_eligibility"]
        missing_eligibility = [
            key for key in ("claim_id", "status", "reason") if not eligibility.get(key)
        ]
        if missing_eligibility:
            raise CardError(
                f"{path.name}: published_anomaly_eligibility missing "
                f"{missing_eligibility}"
            )
        if eligibility["status"] not in VALID_DENOMINATOR_STATUSES:
            raise CardError(
                f"{path.name}: eligibility status must be one of "
                f"{sorted(VALID_DENOMINATOR_STATUSES)}"
            )

        # A rationale of a few words is a label, not a mechanism. The threshold is
        # crude but it catches the failure mode it is aimed at: filling the field
        # to satisfy the check.
        if len(str(data["economic_rationale"]).split()) < 10:
            raise CardError(
                f"{path.name}: economic_rationale is too short to state a "
                "mechanism. Describe why this should predict returns."
            )

        card = cls(
            factor_id=data["factor_id"],
            name=data["name"],
            category=data["category"],
            economic_rationale=str(data["economic_rationale"]).strip(),
            persistence_conditions=str(data["persistence_conditions"]).strip(),
            definition=str(data["definition"]).strip(),
            timing=timing,
            falsification=list(falsification),
            references=list(references),
            published_anomaly_eligibility=dict(eligibility),
            raw=data,
        )
        expected_status = {
            "EXACT_REPLICATION": "INCLUDED",
            "DOCUMENTED_VARIANT": "INCLUDED",
            "UNVERIFIED": "PENDING",
            "UNSUPPORTED_LINEAGE": "EXCLUDED",
        }[card.lineage_status]
        if eligibility["status"] != expected_status:
            raise CardError(
                f"{path.name}: eligibility {eligibility['status']} conflicts with "
                f"derived lineage {card.lineage_status}; expected {expected_status}"
            )
        return card


@dataclass(frozen=True)
class Factor:
    """A registered factor: a card plus the function that computes it."""

    card: HypothesisCard
    compute: Callable[..., pd.DataFrame]
    # Fundamental tags the factor reads, declared so measure_naive_trap and the
    # read-path check know which tags this factor touches. A factor that reads a
    # tag it did not declare will be caught by the test that compares
    # declarations against the access log.
    tags: tuple[str, ...] = ()
    # Minimum days between the filing date and the signal date. Some factors
    # deliberately require a reporting lag beyond the physical constraint;
    # stating it here lets the look-ahead check enforce it.
    filing_lag_days: int = 0
    # (low, high) bounds this factor's raw values are physically capable of
    # taking, or None.
    #
    # NONE MEANS UNDEFINED, NOT PASSED. The two are different states and the
    # report distinguishes them: a factor with no declared range has not been
    # checked, and saying so is the same discipline that keeps an unknown share
    # count null instead of zero. Reading None as "fine" would make the check
    # weakest exactly where nobody has thought about the factor yet.
    #
    # The bounds are physical, not statistical -- the widest values the quantity
    # could take and still mean what its name says. A range fitted to observed
    # data would move whenever the data moved, and would have accepted the
    # market cap that caused incident 12.
    plausible_range: tuple[float, float] | None = None

    @property
    def factor_id(self) -> str:
        return self.card.factor_id

    @property
    def category(self) -> str:
        return self.card.category

    @property
    def uses_fundamentals(self) -> bool:
        return bool(self.tags)


_REGISTRY: dict[str, Factor] = {}


def register(
    factor_id: str,
    tags: tuple[str, ...] = (),
    filing_lag_days: int = 0,
    plausible_range: tuple[float, float] | None = None,
) -> Callable:
    """Decorator registering a factor. The card must already exist.

    Requiring the card file at import time makes the ordering explicit: the
    hypothesis is written first, then the implementation. A factor whose card
    appears afterwards has had its falsification criteria written with the
    results already in view, which is the thing the card exists to prevent.
    """

    def decorator(fn: Callable[..., pd.DataFrame]) -> Callable[..., pd.DataFrame]:
        card_path = CARDS_DIR.joinpath(f"{factor_id}.yaml")
        if not card_path.is_file():
            raise CardError(
                f"no hypothesis card at {card_path}. Write the card before the "
                "implementation: its falsification criteria are only meaningful "
                "if they predate the results."
            )
        card = HypothesisCard.from_yaml(card_path)
        if card.factor_id != factor_id:
            raise CardError(
                f"card factor_id {card.factor_id!r} does not match registration "
                f"{factor_id!r}"
            )
        if factor_id in _REGISTRY:
            raise CardError(f"factor {factor_id!r} is already registered")

        if plausible_range is not None:
            lo, hi = plausible_range
            if not lo < hi:
                raise CardError(
                    f"{factor_id}: plausible_range {plausible_range!r} is not "
                    "ordered (low, high)"
                )

        _REGISTRY[factor_id] = Factor(
            card=card,
            compute=fn,
            tags=tags,
            filing_lag_days=filing_lag_days,
            plausible_range=plausible_range,
        )
        return fn

    return decorator


def get(factor_id: str) -> Factor:
    if factor_id not in _REGISTRY:
        raise KeyError(f"factor {factor_id!r} is not registered")
    return _REGISTRY[factor_id]


def all_factors() -> dict[str, Factor]:
    return dict(_REGISTRY)


def by_category() -> dict[str, list[Factor]]:
    out: dict[str, list[Factor]] = {}
    for f in _REGISTRY.values():
        out.setdefault(f.category, []).append(f)
    return {k: sorted(v, key=lambda f: f.factor_id) for k, v in sorted(out.items())}


def clear() -> None:
    """Empty the registry. For tests only."""
    _REGISTRY.clear()


def load_all() -> dict[str, Factor]:
    """Import every module in this package so its factors self-register."""
    import importlib
    import pkgutil

    package_dir = Path(__file__).resolve().parent
    for mod in pkgutil.iter_modules([str(package_dir)]):
        if mod.name.startswith("_") or mod.name == "registry":
            continue
        importlib.import_module(f"{__package__}.{mod.name}")
    return all_factors()


def summary_table() -> pd.DataFrame:
    """One row per registered factor, for the README and the report header."""
    rows = []
    for f in sorted(_REGISTRY.values(), key=lambda f: (f.category, f.factor_id)):
        rows.append(
            {
                "factor_id": f.factor_id,
                "category": f.category,
                "name": f.card.name,
                "uses_fundamentals": f.uses_fundamentals,
                "tags": ", ".join(f.tags),
                "filing_lag_days": f.filing_lag_days,
                "n_falsification_criteria": len(f.card.falsification),
                "lineage_status": f.card.lineage_status,
                "denominator_status": f.card.published_anomaly_eligibility["status"],
                # Rendered as text so "undefined" cannot be mistaken for a
                # bound, and so the column reads the same in the report as the
                # state it describes.
                "plausible_range": (
                    "undefined"
                    if f.plausible_range is None
                    else f"{f.plausible_range[0]:g} .. {f.plausible_range[1]:g}"
                ),
                "reference": (
                    f.card.references[0]["citation"] if f.card.references else ""
                ),
            }
        )
    return pd.DataFrame(rows)


def published_anomaly_denominator(
    claim_id: str = "published_anomaly_survival_v1",
) -> dict:
    """Return the visible, versioned composition of a headline denominator."""
    definitions = yaml.safe_load(DENOMINATORS_FILE.read_text(encoding="utf-8"))
    claim = definitions["claims"].get(claim_id)
    if claim is None:
        raise CardError(f"unknown denominator claim_id {claim_id!r}")

    cards = [factor.card for factor in _REGISTRY.values()]
    relevant = [
        card
        for card in cards
        if card.published_anomaly_eligibility["claim_id"] == claim_id
    ]
    by_status = {
        status: sorted(
            card.factor_id
            for card in relevant
            if card.published_anomaly_eligibility["status"] == status
        )
        for status in sorted(VALID_DENOMINATOR_STATUSES)
    }
    reasons = {
        card.factor_id: card.published_anomaly_eligibility["reason"]
        for card in relevant
        if card.published_anomaly_eligibility["status"] != "INCLUDED"
    }
    baseline = sorted(claim["baseline_included_factor_ids"])
    current = by_status["INCLUDED"]
    return {
        "claim_id": claim_id,
        "label": claim["label"],
        "baseline_version": claim["baseline_version"],
        "baseline_included": baseline,
        "baseline_n": len(baseline),
        "current_included": current,
        "current_n": len(current),
        "delta_n": len(current) - len(baseline),
        "removed_since_baseline": sorted(set(baseline) - set(current)),
        "added_since_baseline": sorted(set(current) - set(baseline)),
        "excluded": by_status["EXCLUDED"],
        "pending": by_status["PENDING"],
        "reasons": reasons,
    }
