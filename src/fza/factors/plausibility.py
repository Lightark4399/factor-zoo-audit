"""Raw-output plausibility declarations, not proof of input correctness."""

import math
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PlausibilityRule:
    rule_id: str
    kind: str
    severity: str
    lower: float | None
    upper: float | None
    rationale: str

    def __post_init__(self):
        if not self.rule_id.strip() or not self.rationale.strip():
            raise ValueError("rule_id and rationale must be nonblank")
        if self.kind not in {"domain", "construction", "economic"}:
            raise ValueError("unknown plausibility kind")
        if self.severity not in {"error", "warning"}:
            raise ValueError("unknown plausibility severity")
        for bound in (self.lower, self.upper):
            if bound is not None and not math.isfinite(bound):
                raise ValueError("use None, not infinity, for an unbounded side")
        if self.lower is not None and self.upper is not None and self.lower > self.upper:
            raise ValueError("lower must not exceed upper")

    def to_dict(self):
        return asdict(self)


def evaluate_rule(rule, raw, max_share=0.01):
    """Inclusive output bounds. Domain/construction violations have zero tolerance."""
    if not 0 <= max_share <= 1:
        raise ValueError("max_share must be between zero and one")
    values = pd.to_numeric(raw["value"], errors="coerce")
    finite = np.isfinite(values)
    result = {**rule.to_dict(), "scope": "post_universe_raw_output",
              "n_rows": len(raw), "n_values": int(finite.sum()),
              "n_nonfinite_or_missing": int((~finite).sum()),
              "n_outside": None, "share_outside": None, "blocking": False}
    if rule.lower is None and rule.upper is None:
        return {**result, "status": "DECLARED_UNBOUNDED"}
    if not finite.any():
        return {**result, "status": "NO_FINITE_VALUES"}
    outside = finite & False
    if rule.lower is not None:
        outside |= finite & (values < rule.lower)
    if rule.upper is not None:
        outside |= finite & (values > rule.upper)
    share = float(outside.sum() / finite.sum())
    tolerance = max_share if rule.kind == "economic" else 0.0
    breached = share > tolerance
    return {**result, "status": "VIOLATION" if breached else "WITHIN_TOLERANCE",
            "n_outside": int(outside.sum()), "share_outside": share,
            "max_share": tolerance, "blocking": breached and rule.severity == "error"}
