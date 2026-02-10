.PHONY: up down stop start logs ps build restart shell-backend shell-frontend \
        backend-db-migrate backend-db-rollback backend-db-upgrade backend-test

up:
	docker compose up --build -d

down:
	docker compose down

restart:
	make down
	make up

logs:
	docker compose logs -f

ps:
	docker compose ps

build:
	docker compose build

shell-backend:
	docker compose exec backend /bin/bash

shell-frontend:
	docker compose exec frontend /bin/sh

backend-db-migrate:
	docker compose exec backend alembic revision --autogenerate -m "$(msg)"
	docker compose exec backend alembic upgrade head

backend-db-rollback:
	docker compose exec backend alembic downgrade -1

backend-db-upgrade:
	docker compose exec backend alembic upgrade head

backend-test:
	docker compose exec backend pytest tests/
