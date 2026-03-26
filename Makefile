PYTHON ?= python3.12
VENV ?= .venv
BIN := $(VENV)/bin

.PHONY: bootstrap install doctor doctor-passive dev demo self-heal quick test structure compose-up compose-down

bootstrap:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install -e ".[dev]"

install: bootstrap

doctor:
	$(BIN)/cellforge doctor

doctor-passive:
	$(BIN)/cellforge doctor --no-fix

dev:
	$(BIN)/cellforge dev

demo:
	$(BIN)/cellforge run --example document-extraction --artifacts .artifacts/document-extraction

self-heal:
	$(BIN)/python scripts/test_structure.py self-heal

quick:
	$(BIN)/python scripts/test_structure.py quick

structure:
	$(BIN)/python scripts/test_structure.py all

test:
	$(BIN)/pytest -q

compose-up:
	docker compose up -d postgres temporal temporal-ui

compose-down:
	docker compose down
