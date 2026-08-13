.PHONY: test static verify demo

PYTHON ?= $(shell command -v python3.11 2>/dev/null || command -v python3)
export PYTHONPATH := src
export PYTHONPYCACHEPREFIX := /tmp/agent-brain-pycache

test:
	$(PYTHON) -m unittest discover -s tests -v

static:
	$(PYTHON) -m compileall -q src tests
	$(PYTHON) scripts/static_check.py
	$(PYTHON) scripts/validate_skills.py

verify: static test

demo:
	$(PYTHON) scripts/demo.py
