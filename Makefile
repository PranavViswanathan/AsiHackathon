# AirFlow — developer entrypoints.
# Run `make` or `make help` to see available targets.

PYTHON   ?= python3
VENV     := .venv
VENV_BIN := $(VENV)/bin
PORT     ?= 8000
SCENARIO ?= asked_at_2025-05-29T21:00:00Z
SCENARIO_DIR := ./data/hackathon_data_bundle/$(SCENARIO)

.DEFAULT_GOAL := help
.PHONY: help venv install install-py install-web env build build-wind export-web run-full backend frontend dev test clean clean-all

help: ## Show this help
	@echo "AirFlow targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Vars: PORT=$(PORT)  SCENARIO=$(SCENARIO)"

venv: ## Create the Python virtualenv (.venv)
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	@echo "venv ready at $(VENV)"

install: install-py install-web ## Install all backend and frontend deps

install-py: venv ## Install Python deps into .venv
	$(VENV_BIN)/pip install --upgrade pip
	$(VENV_BIN)/pip install -r requirements.txt

install-web: ## Install frontend deps (npm)
	@if [ -f frontend/package.json ]; then \
		cd frontend && npm install; \
	else \
		echo "skip: frontend/package.json not found yet (scaffold the Next.js app first)"; \
	fi

env: ## Create .env from .env.example if missing
	@test -f .env || (cp .env.example .env && echo "created .env")
	@echo "SCENARIO_DIR=$(SCENARIO_DIR)"

build: ## Run the precompute pipeline for $(SCENARIO) -> data/artifacts/<snapshot>/
	$(VENV_BIN)/python -m src.build --scenario-dir $(SCENARIO_DIR)

build-wind: ## Build with Open-Meteo winds (fetched once, cached to wind_cache.npz)
	$(VENV_BIN)/python -m src.build --scenario-dir $(SCENARIO_DIR) --wind

export-web: ## Export lean static JSON for the frontend ($(SCENARIO))
	$(VENV_BIN)/python -m src.export_web --snapshot $(SCENARIO)

run-full: ## One command: install, wind build, export, then run backend + frontend
	$(MAKE) install
	$(MAKE) env
	$(MAKE) build-wind
	$(MAKE) export-web
	$(MAKE) dev

backend: ## Run the FastAPI backend (reload) on $(PORT)
	SCENARIO_DIR=$(SCENARIO_DIR) $(VENV_BIN)/uvicorn backend.main:app --reload --port $(PORT)

frontend: ## Run the Next.js frontend dev server (:3000)
	@if [ -f frontend/package.json ]; then \
		cd frontend && npm run dev; \
	else \
		echo "skip: frontend/package.json not found yet (scaffold the Next.js app first)"; \
	fi

dev: ## Run backend and frontend together (Ctrl-C stops both)
	@echo "Starting backend (:$(PORT)) and frontend (:3000)..."
	@trap 'kill 0' INT TERM EXIT; \
	SCENARIO_DIR=$(SCENARIO_DIR) $(VENV_BIN)/uvicorn backend.main:app --reload --port $(PORT) & \
	( [ -f frontend/package.json ] && cd frontend && npm run dev || echo "frontend not scaffolded yet" ) & \
	wait

test: ## Run the Python test suite
	$(VENV_BIN)/pytest -q

clean: ## Remove caches and generated artifacts
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache data/artifacts frontend/public/data
	@echo "cleaned caches and artifacts"

clean-all: clean ## Also remove .venv and frontend/node_modules
	rm -rf $(VENV) frontend/node_modules frontend/.next
	@echo "removed venv and node_modules"
