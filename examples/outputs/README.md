# Output status

`demo_report.txt` is an earlier synthetic demonstration, not a freshness
guarantee for the current code. It labels its numbers `NOT findings`. Fresh B
acceptance and the full-grid selected-200 archive are tracked in
`../../VALIDATION_20260907.md`; interrupted attempts are not completed artifacts.

`pre_definition_audit_real_report.txt` preserves the former 30-company report
exactly as generated before the annual asset-growth, volatility rename, ROE
lineage, universe, missing-data, and date-semantics corrections. Its source
database (`data/fza.duckdb`) is no longer present, so its values cannot be
regenerated or used as evidence under the current definitions.

The only local real-data store now available is `data/fza_200.duckdb`. Its own
ingestion provenance declares `"run_purpose": "diagnostic_scale"` and
`"research_evidence": false`; it is therefore not used to refresh a research
baseline. A new real baseline remains pending until an evidence-eligible store
is rebuilt, at which point the report must record the new dataset identity and
must not compare its numerical changes to the old 30-company run as though only
the factor definitions had changed.
