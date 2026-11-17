ifneq (,$(wildcard ./.env))
    include .env
    export
endif

PROFILE ?= $(COMPOSE_PROFILES)
ifeq ($(PROFILE),)
    PROFILE := local
endif

.PHONY: docker-up docker-down docker-ps docker-restart docker-logs \
        docker-logs-backend docker-logs-frontend docker-shell-backend \
        docker-shell-frontend db-migrate db-upgrade db-rollback test-backend

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
	docker compose logs -f backend-$(PROFILE)

docker-logs-frontend:
	docker compose logs -f frontend-$(PROFILE)

docker-shell-backend:
	docker compose exec backend-$(PROFILE) /bin/bash

docker-shell-frontend:
	docker compose exec frontend-$(PROFILE) /bin/sh

db-migrate:
	@if [ -z "$(msg)" ]; then \
		echo "Ошибка: Не передано сообщение для миграции."; \
		echo "Использование: make db-migrate msg=\"описание\""; \
		exit 1; \
	fi
	docker compose exec backend-$(PROFILE) alembic revision --autogenerate -m "$(msg)"

db-upgrade:
	docker compose exec backend-$(PROFILE) alembic upgrade head

db-rollback:
	docker compose exec backend-$(PROFILE) alembic downgrade -1

test-backend:
	docker compose exec backend-$(PROFILE) pytest tests/