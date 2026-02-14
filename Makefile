.PHONY: up down ps restart logs logs-backend logs-frontend shell-backend shell-frontend \
        db-migrate db-upgrade db-rollback test-backend

up:
	docker compose up --build -d

down:
	docker compose down

ps:
	docker compose ps

restart:
	make down
	make up

logs:
	docker compose logs -f

logs-backend:
	docker compose logs -f backend

logs-frontend:
	docker compose logs -f frontend

shell-backend:
	docker compose exec backend /bin/bash

shell-frontend:
	docker compose exec frontend /bin/sh

db-migrate:
	docker compose exec backend alembic revision --autogenerate -m "$(msg)"

db-upgrade:
	docker compose exec backend alembic upgrade head

db-rollback:
	docker compose exec backend alembic downgrade -1

test-backend:
	docker compose exec backend pytest tests/
