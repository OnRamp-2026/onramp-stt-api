.PHONY: install dev test lint format typecheck migrate up up-pipeline down logs

install:
	uv pip install -e ".[dev,s3]"

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8001

test:
	pytest tests

lint:
	ruff format --check app scripts tests alembic
	ruff check app scripts tests alembic

format:
	ruff check --fix app scripts tests alembic
	ruff format app scripts tests alembic

typecheck:
	mypy app scripts

migrate:
	alembic upgrade head

up:
	docker compose up --build -d

up-pipeline:
	docker compose --profile pipeline up --build -d

down:
	docker compose --profile pipeline down

logs:
	docker compose --profile pipeline logs -f
