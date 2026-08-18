PYTHON ?= python3.12
VENV := .venv
API_PYTHON := $(VENV)/bin/python
API_UVICORN := $(VENV)/bin/uvicorn

ifneq (,$(wildcard .env))
include .env
export
endif

.PHONY: setup db-up db-down migrate migration-check ingest-demo backfill-entry-teams train-pace diagnose benchmark validate-engineer api web test lint format

setup:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -e '.[dev]'
	npm install

db-up:
	docker compose up -d postgres

db-down:
	docker compose down

migrate:
	cd apps/api && ../../$(VENV)/bin/alembic upgrade head

migration-check:
	cd apps/api && ../../$(VENV)/bin/alembic check

ingest-demo:
	PYTHONPATH=apps/api $(API_PYTHON) -m app.ingestion.cli ingest-season --year $${DEMO_SEASON:-2024}

backfill-entry-teams:
	PYTHONPATH=apps/api $(API_PYTHON) -m app.ingestion.cli backfill-entry-teams

train-pace:
	PYTHONPATH=apps/api $(API_PYTHON) -m app.simulation.cli train-pace --year $${YEAR:-2023} --event "$${EVENT:-Canadian Grand Prix}" --driver-number $${DRIVER_NUMBER:-18} --control-lap $${CONTROL_LAP:-32}

diagnose:
	PYTHONPATH=apps/api $(API_PYTHON) -m app.simulation.cli diagnose

benchmark:
	PYTHONPATH=apps/api $(API_PYTHON) -m app.simulation.cli benchmark

validate-engineer:
	PYTHONPATH=apps/api $(API_PYTHON) -m app.simulation.cli validate-engineer

api:
	$(API_UVICORN) app.main:app --app-dir apps/api --reload

web:
	npm run dev

test:
	$(VENV)/bin/pytest
	npm test

lint:
	$(VENV)/bin/ruff check apps/api
	npm run lint

format:
	$(VENV)/bin/ruff format apps/api
	npm run format
