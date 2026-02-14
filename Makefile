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
	docker compose logs -f backend-dev

logs-frontend:
	docker compose logs -f frontend-dev

shell-backend:
	docker compose exec backend-dev /bin/bash

shell-frontend:
	docker compose exec frontend-dev /bin/sh

db-migrate:
	docker compose exec backend-dev alembic revision --autogenerate -m "$(msg)"

db-upgrade:
	docker compose exec backend-dev alembic upgrade head

db-rollback:
	docker compose exec backend-dev alembic downgrade -1

test-backend:
	docker compose exec backend-dev pytest tests/
