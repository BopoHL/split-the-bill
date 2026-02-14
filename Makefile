.PHONY: docker-up docker-down docker-ps docker-restart docker-logs docker-logs-backend docker-logs-frontend docker-shell-backend docker-shell-frontend \
        db-migrate db-upgrade db-rollback test-backend

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down

docker-ps:
	docker compose ps

docker-restart:
	docker compose down
	docker compose up --build -d

docker-logs:
	docker compose logs -f

docker-logs-backend:
	docker compose logs -f backend-dev

docker-logs-frontend:
	docker compose logs -f frontend-dev

docker-shell-backend:
	docker compose exec backend-dev /bin/bash

docker-shell-frontend:
	docker compose exec frontend-dev /bin/sh

db-migrate:
	docker compose exec backend-dev alembic revision --autogenerate -m "$(msg)"

db-upgrade:
	docker compose exec backend-dev alembic upgrade head

db-rollback:
	docker compose exec backend-dev alembic downgrade -1

test-backend:
	docker compose exec backend-dev pytest tests/
