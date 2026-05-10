# SafeLink Chatbot — make targets.
#
# These wrap the most common dev tasks so engineers don't have to memorise
# pytest invocations or remember which script to run after editing the KB.
#
# Note: the validate-kb-fast variant skips URL HEAD checks for tight loops;
# CI uses the full `make validate-kb`.

.PHONY: help install run test test-kb validate-kb validate-kb-fast migrate-kb

PYTHON ?= python

help:
	@echo "Targets:"
	@echo "  install            pip install -r requirements.txt"
	@echo "  run                uvicorn main:app --reload --port 8000 (DEBUG=true)"
	@echo "  test               pytest tests/"
	@echo "  test-kb            pytest tests/test_kb_*.py tests/test_retrieval.py"
	@echo "  validate-kb        full schema + URL HEAD check"
	@echo "  validate-kb-fast   schema only (skip HEAD probes)"
	@echo "  migrate-kb         run v1→v2 migrator (idempotent)"

install:
	$(PYTHON) -m pip install -r requirements.txt

run:
	DEBUG=true $(PYTHON) -m uvicorn main:app --reload --port 8000

test:
	$(PYTHON) -m pytest tests/ -v

test-kb:
	$(PYTHON) -m pytest tests/test_kb_schema.py tests/test_kb_migration.py tests/test_retrieval.py -v

validate-kb:
	$(PYTHON) scripts/validate_kb.py

validate-kb-fast:
	$(PYTHON) scripts/validate_kb.py --no-head

migrate-kb:
	$(PYTHON) scripts/migrate_kb_v1_to_v2.py
