.PHONY: dev stop logs migrate seed test shell db-shell sync lock run lint

# ── Local development with uv ────────────────────────────────────────────
sync:
	uv sync --dev

lock:
	uv lock

run:
	uv run uvicorn app.main:app --reload

lint:
	uv run ruff check .

# ── Docker ───────────────────────────────────────────────────────────────
dev:
	docker compose up --build

dev-bg:
	docker compose up --build -d

stop:
	docker compose down

logs:
	docker compose logs -f api worker

migrate:
	docker compose exec api alembic upgrade head

seed:
	docker compose exec api python scripts/seed_db.py

test:
	docker compose exec api pytest tests/ -v

shell:
	docker compose exec api bash

db-shell:
	docker compose exec db psql -U vericlaim -d vericlaim

redis-cli:
	docker compose exec redis redis-cli

flower:
	@echo "Flower UI: http://localhost:5555"
	@open http://localhost:5555 2>/dev/null || xdg-open http://localhost:5555 2>/dev/null || true

download-piper:
	bash scripts/download_piper_model.sh
