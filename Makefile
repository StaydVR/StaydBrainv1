.PHONY: test static benchmark verify demo

PYTHON ?= $(shell command -v python3.11 2>/dev/null || command -v python3.12 2>/dev/null || command -v python3)
export PYTHONPATH := src
export PYTHONPYCACHEPREFIX := /tmp/agent-brain-pycache

test:
	$(PYTHON) -m unittest discover -s tests -v

static:
	$(PYTHON) -m compileall -q src tests
	$(PYTHON) scripts/static_check.py
	$(PYTHON) scripts/validate_skills.py

benchmark:
	$(PYTHON) scripts/retrieval_benchmark.py

verify: static test benchmark

demo:
	$(PYTHON) scripts/demo.py
