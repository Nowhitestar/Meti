PYTHON ?= python3

.PHONY: test

test:
	$(PYTHON) scripts/test_local.py
