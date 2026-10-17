# gold-api — common tasks
# Recipe lines are indented with a tab (see .editorconfig).

PY ?= python3
VENV ?= .venv
PIP := $(VENV)/bin/pip
BIN := $(VENV)/bin

.PHONY: help venv install run test lint fmt smoke docker-build docker-run clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS=":.*?## "}; {printf "  %-14s %s\n", $$1, $$2}'

venv: ## Create the virtual environment
	$(PY) -m venv $(VENV)

install: ## Install runtime + dev dependencies
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt -r requirements-dev.txt

run: ## Run the API with auto-reload on :8000
	$(BIN)/uvicorn app.main:app --reload --port 8000

test: ## Run the hermetic test suite
	$(BIN)/pytest -q

lint: ## Lint with ruff
	$(BIN)/ruff check .

fmt: ## Auto-fix lint findings
	$(BIN)/ruff check . --fix

smoke: ## One-shot offline refresh, prints a summary (no server)
	$(BIN)/python scripts/smoke_test.py

docker-build: ## Build the container image
	docker build -t gold-api .

docker-run: ## Run the container on :8000 with a data volume
	docker run --rm -p 8000:8000 -v gold-api-data:/data gold-api

clean: ## Remove the venv and caches
	rm -rf $(VENV) .pytest_cache .ruff_cache data
