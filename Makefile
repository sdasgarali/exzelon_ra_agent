# NeuraLeads AI — Development Commands
.PHONY: help dev backend frontend test lint migrate clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

dev: ## Start both backend and frontend (requires two terminals)
	@echo "Run in separate terminals:"
	@echo "  make backend"
	@echo "  make frontend"

backend: ## Start FastAPI backend on port 8000
	cd backend && uvicorn app.main:app --reload --port 8000

frontend: ## Start Next.js frontend on port 3000
	cd frontend && npm run dev

test: ## Run all backend tests
	cd backend && python -m pytest -v

test-unit: ## Run unit tests only
	cd backend && python -m pytest -m unit -v

test-integration: ## Run integration tests only
	cd backend && python -m pytest -m integration -v

test-cov: ## Run tests with coverage report (min 75%)
	cd backend && python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=75

lint: ## Lint frontend
	cd frontend && npm run lint

build: ## Build frontend for production
	cd frontend && npm run build

migrate: ## Generate new Alembic migration (usage: make migrate msg="description")
	cd backend && python -m alembic revision --autogenerate -m "$(msg)"

migrate-up: ## Apply all pending migrations
	cd backend && python -m alembic upgrade head

migrate-down: ## Rollback last migration
	cd backend && python -m alembic downgrade -1

migrate-history: ## Show migration history
	cd backend && python -m alembic history

install: ## Install all dependencies
	cd backend && pip install -r requirements.txt
	cd frontend && npm install

clean: ## Remove build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf frontend/.next frontend/node_modules/.cache
