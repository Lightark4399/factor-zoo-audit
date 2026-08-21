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
from pathlib import Path

import pandas as pd
import yaml

CARDS_DIR = Path(__file__).resolve().parent / "cards"

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
)

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
    references: list[str]
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: Path) -> HypothesisCard:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        missing = [f for f in REQUIRED_CARD_FIELDS if f not in data or data[f] in (None, "")]
        if missing:
            raise CardError(f"{path.name}: missing or empty field(s): {missing}")

        if data["category"] not in VALID_CATEGORIES:
            raise CardError(
                f"{path.name}: category {data['category']!r} not in {sorted(VALID_CATEGORIES)}"
            )

        timing = data["timing"]
        for key in ("signal_computed", "earliest_execution"):
            if key not in timing:
                raise CardError(f"{path.name}: timing.{key} is required")

        falsification = data["falsification"]
        if not isinstance(falsification, list) or not falsification:
            raise CardError(
                f"{path.name}: falsification must be a non-empty list. A factor "
                "with no stated way to fail cannot be tested."
            )

        # A rationale of a few words is a label, not a mechanism. The threshold is
        # crude but it catches the failure mode it is aimed at: filling the field
        # to satisfy the check.
        if len(str(data["economic_rationale"]).split()) < 10:
            raise CardError(
                f"{path.name}: economic_rationale is too short to state a "
                "mechanism. Describe why this should predict returns."
            )

        return cls(
            factor_id=data["factor_id"],
            name=data["name"],
            category=data["category"],
            economic_rationale=str(data["economic_rationale"]).strip(),
            persistence_conditions=str(data["persistence_conditions"]).strip(),
            definition=str(data["definition"]).strip(),
            timing=timing,
            falsification=list(falsification),
            references=list(data["references"]),
            raw=data,
        )


@dataclass(frozen=True)
class Factor:
    """A registered factor: a card plus the function that computes it."""

    card: HypothesisCard
    compute: Callable[..., pd.DataFrame]
    # Fundamental tags the factor reads, declared so assert_no_lookahead knows
    # what to check. A factor that reads a tag it did not declare will be caught
    # by the test that compares declarations against the access log.
    tags: tuple[str, ...] = ()
    # Minimum days between the filing date and the signal date. Some factors
    # deliberately require a reporting lag beyond the physical constraint;
    # stating it here lets the look-ahead check enforce it.
    filing_lag_days: int = 0

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
) -> Callable:
    """Decorator registering a factor. The card must already exist.

    Requiring the card file at import time makes the ordering explicit: the
    hypothesis is written first, then the implementation. A factor whose card
    appears afterwards has had its falsification criteria written with the
    results already in view, which is the thing the card exists to prevent.
    """

    def decorator(fn: Callable[..., pd.DataFrame]) -> Callable[..., pd.DataFrame]:
        card_path = CARDS_DIR / f"{factor_id}.yaml"
        if not card_path.exists():
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

        _REGISTRY[factor_id] = Factor(
            card=card, compute=fn, tags=tags, filing_lag_days=filing_lag_days
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
                "reference": f.card.references[0] if f.card.references else "",
            }
        )
    return pd.DataFrame(rows)
