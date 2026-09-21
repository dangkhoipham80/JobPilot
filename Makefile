# JobPilot dev tasks. See PLAN.md / CLAUDE.md.
.PHONY: help venv install install-all db-up db-down migrate api web crawl slack test config lint

# The repo is edited on Windows and on macOS/Linux, and the two put the venv's
# interpreter in different places (Scripts\ vs bin/). Resolve it once here, and
# call every tool as `$(PY) -m <tool>` rather than by bare name: that way the
# targets use the venv whether or not it has been activated, instead of silently
# running whichever python happens to be first on PATH.
VENV := .venv
PY := $(if $(wildcard $(VENV)/bin/python),$(VENV)/bin/python,$(VENV)/Scripts/python)

help:
	@echo "JobPilot targets:"
	@echo "  make install     - create .venv and install base + dev deps (Phase 0)"
	@echo "  make install-all - install every phase extra (data,api,crawler,tailor,slack)"
	@echo "  make config      - validate & print resolved config (Phase 0)"
	@echo "  make db-up     - start Postgres (docker-compose, or brew services on macOS)"
	@echo "  make db-down   - stop Postgres"
	@echo "  make migrate   - alembic upgrade head (Phase 2+)"
	@echo "  make api       - run FastAPI backend (Phase 2+)"
	@echo "  make web       - run React dashboard (Phase 4+)"
	@echo "  make crawl     - crawl jobs into DB (Phase 3+)"
	@echo "  make slack     - run Slack bot, secondary channel (Phase 7+)"
	@echo "  make test      - run pytest"
	@echo "  make dev       - db-up + api together (Phase 4+); run 'make web' in a second terminal"

install:
	python3 -m venv $(VENV) || python -m venv $(VENV)
	$(PY) -m pip install -U pip
	$(PY) -m pip install -e ".[dev]"

install-all:
	$(PY) -m pip install -e ".[all,dev]"

config:
	$(PY) -m jobpilot.cli config

# Postgres runs in Docker where there is Docker, and as a Homebrew service on a
# Mac that has none. Both land on the same 127.0.0.1:5432, so DATABASE_URL does
# not care which one answered — but `make db-up` says which it used, because a
# database started by the other mechanism holds different data.
db-up:
	@if command -v docker >/dev/null 2>&1; then \
		echo "-> docker-compose"; docker-compose up -d postgres; \
	elif command -v brew >/dev/null 2>&1; then \
		echo "-> brew services (postgresql@17)"; brew services start postgresql@17; \
	else \
		echo "No docker and no brew: start PostgreSQL yourself, then re-run."; exit 1; \
	fi

db-down:
	@if command -v docker >/dev/null 2>&1; then \
		docker-compose down; \
	elif command -v brew >/dev/null 2>&1; then \
		brew services stop postgresql@17; \
	fi

migrate:
	$(PY) -m alembic upgrade head

api:
	$(PY) -m uvicorn jobpilot.api.main:app --reload --port 8000

web:
	cd web && npm run dev

crawl:
	$(PY) -m jobpilot.cli crawl

slack:
	$(PY) -m jobpilot.slack.app

test:
	$(PY) -m pytest jobpilot/tests

lint:
	$(PY) -m ruff check jobpilot && $(PY) -m black --check jobpilot

dev: db-up api
