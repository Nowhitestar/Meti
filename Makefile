.PHONY: test lint typecheck unit smoke clean

test: lint typecheck unit smoke

unit:
	python3 -m pytest -q

lint:
	python3 -m ruff check .

typecheck:
	python3 -m mypy core

smoke:
	python3 scripts/test_local.py

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache __pycache__
	find . -name "__pycache__" -type d -exec rm -rf {} +
	find . -name "*.pyc" -delete
