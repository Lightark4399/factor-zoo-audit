"""Create one immutable local input subset and export the two source anchors."""
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fza.store import Store  # noqa: E402


def main():
    destination = ROOT / ".diagnostic-envs" / "real-stage-0913"
    destination.mkdir(exist_ok=False)
    database = ROOT / "data" / "fza_200.duckdb"
    source = Store(str(database), read_only=True)
    subset = Store(str(destination / "subset.duckdb"))
    try:
        roster = source.con.execute(
            "SELECT * FROM securities WHERE accounting_standard = 'us-gaap' "
            "ORDER BY ticker, cik LIMIT 20"
        ).df()
        source.con.register("selected_roster", roster)
        prices = source.con.execute(
            "SELECT p.* FROM prices p WHERE ticker IN (SELECT ticker FROM selected_roster) "
            "ORDER BY ticker, trade_date"
        ).df()
        fundamentals = source.con.execute(
            "SELECT f.* FROM fundamentals f WHERE cik IN (SELECT cik FROM selected_roster) "
            "ORDER BY cik, tag, period_start, period_end, filed, form, accession, frame"
        ).df()
        subset.load_securities(roster)
        subset.load_prices(prices)
        subset.load_fundamentals(fundamentals)
        counts = {table: subset.con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                  for table in ("securities", "prices", "fundamentals")}
    finally:
        source.close()
        subset.close()
    anchors = {}
    for short in ("0bd03bf", "de1e836"):
        commit = subprocess.check_output(["git", "rev-parse", short], cwd=ROOT, text=True).strip()
        archive = destination / f"{short}.zip"
        subprocess.run(["git", "archive", "--format=zip", f"--output={archive}",
                        commit, "src"], cwd=ROOT, check=True)
        target = destination / short
        target.mkdir()
        with zipfile.ZipFile(archive) as contents:
            for item in contents.infolist():
                resolved = (target / item.filename).resolve()
                if not resolved.is_relative_to(target.resolve()):
                    raise ValueError("Archive path escapes source directory")
            contents.extractall(target)
        anchors[short] = commit
    manifest = dict(
        source_sha256=hashlib.sha256(database.read_bytes()).hexdigest(),
        subset_sha256=hashlib.sha256((destination / "subset.duckdb").read_bytes()).hexdigest(),
        roster=roster[["ticker", "cik"]].to_dict("records"), counts=counts, anchors=anchors,
        selection="first 20 us-gaap ordered ticker,cik; all stored history",
        plan_sha256=hashlib.sha256(
            (ROOT / "PERFORMANCE_REAL_INPUT_PLAN.md").read_bytes()).hexdigest(),
    )
    with (destination / "inputs.json").open("x", encoding="utf-8", newline="\n") as out:
        json.dump(manifest, out, indent=2)
        out.write("\n")
    print(json.dumps(manifest))


if __name__ == "__main__":
    main()
