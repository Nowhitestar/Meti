.PHONY: test lint typecheck unit smoke release-check clean

PYTHON ?= python3

test: lint typecheck unit smoke

unit:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

typecheck:
	$(PYTHON) -m mypy core

smoke:
	$(PYTHON) scripts/test_local.py

release-check:
	$(PYTHON) scripts/check_release.py

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache __pycache__
	find . -name "__pycache__" -type d -exec rm -rf {} +
	find . -name "*.pyc" -delete
