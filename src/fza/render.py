"""Pure report rendering: no store, factor execution or current registry reads."""

from __future__ import annotations

import json
import textwrap
from types import SimpleNamespace

import pandas as pd

from .pipeline.vintage import SENSITIVITY_NOTICE
from .qualification import qualification_lines
from .reporting import breadth_diagnostic

WIDTH = 84


def _rule(char="-", width=WIDTH):
    return char * width


def _header(title):
    return f"\n{_rule('=')}\n{title}\n{_rule('=')}"


def wrap_report_line(text, width=WIDTH):
    """Preserve short/table rows; wrap long rows without deleting tokens."""
    result = []
    for line in text.split("\n"):
        if len(line) <= width:
            result.append(line)
            continue
        indent = len(line) - len(line.lstrip())
        result.extend(textwrap.wrap(
            line, width=width, subsequent_indent=" " * min(indent + 2, width // 2),
            break_long_words=True, break_on_hyphens=False,
            replace_whitespace=False,
        ))
    return result


def validate_report_width(text, width=WIDTH):
    for number, line in enumerate(text.splitlines(), 1):
        if len(line) > width:
            raise ValueError(f"line {number}: {len(line)} columns exceeds {width}")


def _protocol_view(record):
    if record is None:
        return None
    # JSON null remains null in the archive. The display adapter restores the
    # legacy NaN spelling for undefined numerical statistics, never a zero.
    summary = {key: float("nan") if value is None else value
               for key, value in record.items()}
    values = dict(summary)
    values["summary"] = summary
    return SimpleNamespace(**values)


def _run_view(record):
    values = dict(record)
    values["protocol"] = _protocol_view(record["protocol"])
    values["universe_filter"] = SimpleNamespace(**record["universe_filter"])
    values["label_join"] = SimpleNamespace(**record["label_join"])
    return SimpleNamespace(**values)


def render_report(bundle, *, local_sensitivity_notice=True):
    """Render captured results; missing presentation inputs fail explicitly."""
    presentation = bundle["presentation"]
    info = bundle["data_summary"]
    evidence = bundle["evidence"]
    mode = evidence["mode"]
    args = SimpleNamespace(db=presentation["database_display"])
    lines = []

    def emit(text=""):
        lines.extend(wrap_report_line(text))

    emit(_rule("="))
    emit("FACTOR ZOO AUDIT".center(WIDTH))
    emit(_rule("="))
    emit()

    if mode == "fixture":
        emit("  DATA: synthetic fixtures (no ingested store found)")
        emit()
        emit("  The numbers below are NOT findings. Fixture prices are a random")
        emit("  walk, so no factor can predict them and none is meant to. What")
        emit("  this run demonstrates is that the machinery behaves: the")
        emit("  point-in-time view returns the pre-restatement value, the")
        emit("  look-ahead check fires when it should, and the vintage comparison")
        emit("  isolates the filing constraint.")
        emit()
        emit("  For real numbers, ingest first:")
        emit("    python -m fza.ingest.run --user-agent 'Name you@example.com'")
    else:
        emit(f"  DATA: {args.db}")
    emit()
    for line in qualification_lines(evidence):
        emit("  " + line)
    emit(f"  reasons: {', '.join(evidence['reasons'])}")
    if mode == "real":
        emit(f"  sidecar binding: {evidence['sidecar_binding']}")
        emit("  declared research_evidence: " + json.dumps(evidence['declared_research_evidence']))
        emit("  declared run purpose: " + json.dumps(evidence['declared_run_purpose']))
        emit(f"  database SHA-256: {evidence['database_sha256']}")
        emit(f"  sidecar SHA-256: {evidence['sidecar_sha256']}")
        emit("  declared survivorship-prone source share: " +
             json.dumps(evidence['declared_survivorship_prone_share']))
        emit("  Source share is NOT the magnitude or direction of survivorship bias.")
        emit("  Sidecar declarations, even true or hash-matched, do not certify research.")
    emit()
    emit(f"  securities     {info['securities']:>10,}")
    emit(
        f"  with us-gaap   {info['securities_usgaap']:>10,}   "
        f"(fundamental factors see only these)"
    )
    other = {
        k: v for k, v in info['securities_by_standard'].items() if k != 'us-gaap'
    }
    if other:
        detail = ", ".join(f"{v} {k}" for k, v in sorted(other.items()))
        emit(f"  excluded       {detail:>10}   "
             f"(prices only -- no readable fundamentals)")
    emit(f"  fundamentals   {info['fundamentals']:>10,}")
    emit(f"  prices         {info['prices']:>10,}")
    rate = ("unavailable" if info['restatement_rate'] is None
            else f"{info['restatement_rate']:.1%}")
    emit(f"  restatements   {info['restatements']:>10,}   "
         f"({rate} of fundamental rows)")
    emit(f"  price history  {info['first_date']} .. {info['last_date']}")

    environment = bundle["environment"]
    emit(_header("RESEARCH ENVIRONMENT"))
    emit()
    emit(f"  {'Python':<14}{environment['python']}")
    for package in ("pandas", "numpy", "scipy", "statsmodels"):
        emit(f"  {package:<14}{environment[package]}")
    emit(f"  {'lock':<14}{environment['lock_file']}")
    emit(f"  {'lock SHA-256':<14}{environment['lock_sha256']}")
    emit(f"  {'lock status':<14}{environment['lock_status']}")
    if environment["lock_mismatches"]:
        for package, versions in environment["lock_mismatches"].items():
            emit(
                f"    {package}: installed {versions['installed']}, "
                f"locked {versions['locked']}"
            )
    emit()
    emit("  These are the versions that produced this report. MATCHED means the")
    emit("  four numerical libraries equal the exact shipped research lock;")
    emit("  MISMATCH keeps the report diagnostic and prints every difference.")

    coverage = pd.DataFrame(presentation["price_coverage"],
                            columns=["column", "non_null", "coverage"])
    thin = coverage.loc[coverage["coverage"] < 0.99]
    if len(thin):
        emit(_header("DATA QUALITY"))
        emit()
        emit("  Price columns that are not fully populated. A column at 0.0%")
        emit("  empties every factor that reads it, and the failure surfaces as")
        emit("  'factor produced no values' -- naming the factor, not the column.")
        emit()
        emit(f"  {'column':<16}{'non-null':>12}{'coverage':>12}")
        for _, row in thin.iterrows():
            emit(
                f"  {row['column']:<16}{int(row['non_null']):>12,}"
                f"{row['coverage']:>11.1%}"
            )

    emit(_header("REGISTERED FACTORS"))
    emit()
    table = pd.DataFrame(presentation["registered_factors"])
    emit(
        f"  {'factor':<14}{'category':<14}{'fundamentals':<14}"
        f"{'falsification':>14}{'plausible range':>20}"
    )
    for _, row in table.iterrows():
        emit(
            f"  {row['factor_id']:<14}{row['category']:<14}"
            f"{'yes' if row['uses_fundamentals'] else 'no':<14}"
            f"{row['n_falsification_criteria']:>14}"
            f"{row['plausible_range']:>20}"
        )
    emit()
    emit("  Every factor carries a hypothesis card stating an economic mechanism,")
    emit("  the conditions under which it should persist, and what would falsify")
    emit("  it. Registration fails without one.")
    emit()
    emit("  'plausible range' shows the legacy economic scale guard only.")
    emit("  'undefined': NOT that the factor passed; no legacy range is declared.")
    emit("  It does not describe additional rules.")
    emit("  RAW-OUTPUT PLAUSIBILITY RULES below reports all evaluated declarations.")

    denominator = bundle["denominator"]
    emit(_header("PUBLISHED-ANOMALY DENOMINATOR"))
    emit()
    emit(f"  claim             {denominator['claim_id']}")
    emit(
        f"  current base      {denominator['current_n']} included "
        f"(baseline {denominator['baseline_n']}, delta {denominator['delta_n']:+d})"
    )
    emit(f"  included          {', '.join(denominator['current_included'])}")
    emit(f"  excluded          {', '.join(denominator['excluded']) or 'none'}")
    emit(f"  pending           {', '.join(denominator['pending']) or 'none'}")
    emit(
        "  removed vs base   "
        f"{', '.join(denominator['removed_since_baseline']) or 'none'}"
    )
    for factor_id in denominator["excluded"] + denominator["pending"]:
        emit(f"    {factor_id}: {denominator['reasons'][factor_id]}")
    emit()
    emit("  INCLUDED requires a verified definition-origin citation. PENDING means")
    emit("  the proposed origin has not been checked at a primary-source locator;")
    emit("  EXCLUDED means the implemented quantity is not the published anomaly.")
    emit("  Definition eligibility is separate from outcome evidence; no survival rate")
    emit("  follows from this denominator or from a completed computation.")

    dates = pd.DatetimeIndex(bundle["configuration"]["signal_dates"])
    available_signal_dates = bundle["configuration"]["available_signal_dates"]

    emit(_header("STANDARD PROTOCOL"))
    emit()
    emit("  " + qualification_lines(evidence)[0])
    emit(f"  {len(dates)} signal dates from the monthly grid, "
         f"{dates[0].date() if len(dates) else 'n/a'} .. "
         f"{dates[-1].date() if len(dates) else 'n/a'}")
    if len(dates) < available_signal_dates:
        emit("  SUBSAMPLED diagnostic grid: formation shifts count selected dates.")
        emit("  This is not definition-equivalent to the full monthly run.")
    emit()
    emit(
        f"  {'factor':<14}{'IC':>10}{'LS Sharpe':>11}"
        f"{'monotone':>10}{'dates':>7}{'as-of held':>11}  status"
    )

    runs = {}
    failures = {}
    for factor_id, record in bundle["factors"].items():
        if record["computation_status"] != "COMPLETED":
            status = record["computation_status"]
            failures[factor_id] = status
            emit(f"  {factor_id:<14}{'--':>10}{'--':>11}"
                 f"{'--':>10}{'--':>7}{'--':>11}  {status}")
            for reason in record.get("failure", {}).get("display_reasons", []):
                emit(f"      {reason}")
            if "failure" not in record:
                emit("      Failure details not captured in this legacy JSON.")
            continue
        run = _run_view(record)
        runs[factor_id] = run
        s = run.protocol.summary
        emit(
            f"  {factor_id:<14}{s['ic_mean']:>+10.4f}{s['ls_sharpe']:>+11.4f}"
            f"{run.protocol.monotonicity_rho:>+10.2f}{run.protocol.n_dates:>7}"
            f"{('yes' if run.read_path_check['ok'] else 'VIOLATION'):>11}  OK"
            f" {breadth_diagnostic(s)['marker']}".rstrip()
        )

    emit()
    emit("  'as-of held' is a check on this code: did every read return only")
    emit("  filings that were already public on the day being forecast, including")
    emit("  any reporting lag the factor declared? A VIOLATION here would void")
    emit("  every number in the row.")
    emit()
    emit("  'status' is whether the factor produced a result at all. OK means the")
    emit("  run completed; it does not mean the factor works. A FAILED row has no")
    emit("  numbers because none were computed -- the run stopped at the check")
    emit("  named in the status, and that row is excluded from every table below.")
    emit("  [B]: a retained quantile group has <= 3 names; [B?]: breadth unavailable.")
    emit("  This display rule was chosen after observing data, using the existing")
    emit("  nominal size multiplier. It changes no samples or metrics; absence of")
    emit("  a flag is not evidence of adequate power or IC validity.")

    emit(_header("RAW-OUTPUT PLAUSIBILITY RULES"))
    emit("  These supplement legacy ranges; they do not verify input provenance.")
    for factor_id, run in runs.items():
        if not run.magnitude_check.get("rules"):
            emit(f"  {factor_id}: UNDECLARED -- no raw-output rule evaluated")
        for rule in run.magnitude_check.get("rules", []):
            emit(f"  {factor_id}: {rule['rule_id']} -- {rule['status']}")
            emit(f"    {rule['kind']} / {rule['severity']}; "
                 f"bounds [{rule['lower']}, {rule['upper']}]")
            for line in textwrap.wrap(rule["rationale"], width=WIDTH - 4):
                emit(f"    {line}")
    emit("  DECLARED_UNBOUNDED is not PASS; no finite magnitude bound was tested.")
    emit("  Missing/nonfinite values are counted, not certified by a finite-value check.")

    emit(_header("HISTORICAL UNIVERSE GATE"))
    emit()
    emit("  Membership is applied to raw factor rows before magnitude checks,")
    emit("  winsorisation and standardisation. An excluded row therefore cannot")
    emit("  alter the score of a security that was eligible on the same date.")
    emit()
    emit(
        f"  {'factor':<14}{'raw rows':>12}{'eligible':>12}"
        f"{'excluded':>12}{'retained':>11}"
    )
    for factor_id, run in runs.items():
        u = run.universe_filter
        emit(
            f"  {factor_id:<14}{u.n_input:>12,}{u.n_output:>12,}"
            f"{u.n_excluded_outside_universe:>12,}{u.retention:>11.1%}"
        )
    emit()
    emit("  'excluded' is reported independently from missing-value cleaning and")
    emit("  label attrition: outside the historical universe is an eligibility")
    emit("  decision, not a missing observation.")
    emit("  For ingested data this is a filing-activity proxy, not verified exchange")
    emit("  membership. It cannot recover securities missing from the initial selection.")

    emit(_header("FACTOR-CONSTRUCTION SAMPLE FILTERS"))
    emit()
    emit("  These are definition-level eligibility rules applied inside a factor,")
    emit("  before the common universe gate and missing-value cleaning.")
    emit()
    emit(f"  {'factor':<14}{'filter':<38}{'input':>9}{'excluded':>11}")
    any_filter = False
    for factor_id, run in runs.items():
        for construction_filter in run.construction_filters:
            any_filter = True
            emit(
                f"  {factor_id:<14}{construction_filter['filter_id']:<38}"
                f"{construction_filter['n_input']:>9,}"
                f"{construction_filter['n_excluded']:>11,}"
            )
            sample = construction_filter.get("excluded_keys", [])[:5]
            if sample:
                shown = ",\n        ".join(
                    f"{row['signal_date']} {row['ticker']} ({row['equity']:g})"
                    for row in sample
                )
                emit(f"      excluded keys: {shown}")
    if not any_filter:
        emit("  none")

    emit(_header("FORWARD-LABEL ATTRITION"))
    emit()
    emit("  Every cleaned signal is left-joined to its realised return before")
    emit("  invalid rows are removed, so an absent label cannot disappear without")
    emit("  a counted reason.")
    emit()
    emit(
        f"  {'factor':<14}{'signals':>12}{'labelled':>12}"
        f"{'dropped':>12}{'retained':>11}"
    )
    for factor_id, run in runs.items():
        label = run.label_join
        emit(
            f"  {factor_id:<14}{label.n_input:>12,}{label.n_output:>12,}"
            f"{label.n_dropped_without_label:>12,}{label.retention:>11.1%}"
        )
        reasons = {
            reason: count
            for reason, count in label.outcome_counts.items()
            if reason != "matched" and count
        }
        if reasons:
            rendered = ", ".join(
                f"{reason}={count:,}" for reason, count in sorted(reasons.items())
            )
            emit(f"    {rendered}")

    emit(_header("CROSS-SECTION BREADTH"))
    emit()
    emit("  Distribution over retained date x quantile groups, not whole cross-sections.")
    emit("  Dropped dates are absent from this distribution. A minimum of 3 means")
    emit("  a retained group had 3 names; it does not explain a dropped date.")
    emit()
    emit(
        f"  {'factor':<14}{'avg':>7}{'min':>7}{'p10':>7}{'median':>9}"
        f"{'p90':>7}{'max':>7}{'dropped':>10}"
    )
    for factor_id, run in runs.items():
        s = run.protocol.summary
        emit(
            f"  {factor_id:<14}{s['names_per_quantile_avg']:>7.1f}"
            f"{s['names_per_quantile_min']:>7}{s['names_per_quantile_p10']:>7.1f}"
            f"{s['names_per_quantile_median']:>9.1f}{s['names_per_quantile_p90']:>7.1f}"
            f"{s['names_per_quantile_max']:>7}"
            f"{s['n_dates_dropped_insufficient_cross_section']:>10}"
        )
    emit()
    emit("  'dropped' counts signal dates present in the aligned panel but absent")
    emit("  from quantile portfolios because the cross-section was too small or")
    emit("  ties prevented all five groups from being formed.")

    emit(_header("THE TRAP, MEASURED"))
    emit()
    emit("  How much would a naive query have read early? This is the hazard the")
    emit("  bitemporal store exists to avoid -- a diagnostic count, not an alpha finding.")
    emit()
    emit(f"  {'factor':<14}{'signal dates':>14}{'exposed':>10}{'trap rows':>12}{'rate':>9}")
    for factor_id, run in runs.items():
        t = run.naive_trap
        if not t.get("n_signal_dates"):
            emit(f"  {factor_id:<14}{'n/a -- reads no fundamentals':>45}")
            continue
        emit(
            f"  {factor_id:<14}{t['n_signal_dates']:>14,}{t['n_dates_exposed']:>10,}"
            f"{t['n_trap_rows']:>12,}{t['exposure_rate']:>9.1%}"
        )

    emit(_header("POINT-IN-TIME VS RESTATED"))
    emit()
    emit("  " + qualification_lines(evidence)[0])
    emit("  Original-process diagnostic: shared dates, arm-specific observations.")
    emit("  Cleaning uses each arm's own sample; shared defects need not cancel.")
    emit("  The gap mixes value/availability/processing changes, not pure revisions.")
    emit("  PASS/FAIL uses a preconfigured directional threshold, not significance.")
    emit("  PASS means no positive-gap trigger, not validated evidence.")
    emit("  Label/holding-period checks are shown per layer; a mismatch blocks gaps.")
    emit()

    for factor_id in bundle["factors"]:
        comp_record = bundle["vintage_comparisons"][factor_id]
        if comp_record["status"] in {"FAILED", "NOT_COMPUTED"}:
            emit(f"  {factor_id}: not compared -- {comp_record['status']}")
            failure = comp_record.get("failure", {})
            emit("    " + failure.get("status", comp_record.get("reason", "unknown")))
            for reason in failure.get("display_reasons", [comp_record.get("reason", "unknown")]):
                emit("    " + reason)
            continue
        comp = SimpleNamespace(
            applicable=comp_record["status"] != "NOT_APPLICABLE",
            pit=_protocol_view(comp_record["pit"]),
            restated=_protocol_view(comp_record["restated"]),
            ic_gap=comp_record["ic_gap"],
            verdict=comp_record["diagnostic_verdict"],
            detail=comp_record["detail"],
        )

        emit(f"  {factor_id}")
        if not comp.applicable:
            for line in textwrap.wrap(comp.verdict, width=WIDTH - 4):
                emit("    " + line)
        else:
            emit(f"    point-in-time IC   {comp.pit.summary['ic_mean']:>+10.4f}")
            emit(f"    restated IC        {comp.restated.summary['ic_mean']:>+10.4f}")
            gap_text = "unavailable" if pd.isna(comp.ic_gap) else f"{comp.ic_gap:+.4f}"
            emit(f"    restated minus PIT {gap_text:>10}")
            verdict = comp.verdict.split(":")[0]
            emit(f"    verdict            {verdict:>10}")
        sample = comp.detail.get("sample_comparison")
        if sample is not None:
            emit(f"    observations       PIT {sample['pit_observations']:,} / "
                 f"restated {sample['restated_observations']:,}")
            emit(f"    shared keys        {sample['common_observations']:,}; "
                 f"PIT-only {sample['pit_only_observations']:,}; "
                 f"restated-only {sample['restated_only_observations']:,}")
            emit(f"    identical keys     {sample['identical_observation_keys']}")
            emit(f"    read-path coverage {comp.detail['read_path_coverage']}")
            emit(f"    IC gap threshold   {comp.detail['material_gap_threshold']:.4f} "
                 "(diagnostic, not significance)")
        for name, layer in comp.detail.get("layers", {}).items():
            gap = "unavailable" if layer["ic_gap"] is None else f"{layer['ic_gap']:+.4f}"
            emit(f"    {name:<20} IC gap {gap} | {layer['status']}")
            emit(f"      label/holding-period: {layer['outcome_identity']['status']}")
            if "source_outcome_identity" in layer:
                emit("      source label/holding-period: "
                     + layer["source_outcome_identity"]["status"])
            if "sample" in layer:
                sample_row = layer["sample"]
                emit(f"      observations: PIT {sample_row['pit_observations']:,} / "
                     f"restated {sample_row['restated_observations']:,}; "
                     f"common {sample_row['common_observations']:,}")
            if "ic" in layer.get("metrics", {}):
                metric = layer["metrics"]["ic"]
                emit(f"      IC dates: PIT {len(metric['pit_dates'])} / "
                     f"restated {len(metric['restated_dates'])}; "
                     f"same {metric['identical_metric_dates']}")
            for line in textwrap.wrap(layer["scope"], width=WIDTH - 6):
                emit("      " + line)
            if layer.get("reason"):
                emit(f"      reason: {layer['reason']}")
        if local_sensitivity_notice and comp.detail.get("layers"):
            emit("    " + SENSITIVITY_NOTICE)
        emit()

    gates = bundle["research_gates"]
    emit(_header("RESEARCH CLAIM GATES"))
    for gate, state in gates.items():
        emit(f"  {gate}: {state['status']} -- {state['reason']}")
    emit("  UNRESOLVED is not a measured bias size; NOT_IMPLEMENTED is not passed.")
    for line in textwrap.wrap(SENSITIVITY_NOTICE, width=WIDTH - 2):
        emit("  " + line)

    emit(_rule("="))
    for line in qualification_lines(evidence):
        emit("  " + line)
    emit("  The vintage gap is conditional on the selected data and label samples;")
    emit("  it does not establish a market-wide effect or cancel shared data defects.")
    emit("  Ingest alone does not qualify research evidence.")
    emit(_rule("="))
    emit()


    rendered = "\n".join(lines)
    validate_report_width(rendered)
    return rendered
