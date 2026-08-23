.PHONY: help install test lint data demo clean

help:
	@echo "install  install with dev extras"
	@echo "test     run the test suite (no network needed)"
	@echo "lint     ruff check"
	@echo "data     download SEC filings and prices into data/fza.duckdb (needs network)"
	@echo "demo     run the pipeline on synthetic fixtures (no network needed)"

install:
	pip install -e ".[dev,ingest]"

test:
	python -m pytest

lint:
	ruff check src tests

# Ingestion is the only step that needs the internet. Everything else, including
# the whole test suite, runs on fixtures -- so a reviewer can verify the
# correctness argument without downloading anything.
data:
	python -m fza.ingest.run --out data/fza.duckdb

# Runs on an ingested store when one exists, and on fixtures otherwise -- so a
# reviewer can see the pipeline work without downloading anything, and CI can
# run it unchanged.
demo:
	python -m fza.demo --outdir examples/outputs

clean:
	rm -rf .pytest_cache **/__pycache__ .ruff_cache
