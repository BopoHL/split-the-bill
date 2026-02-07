.PHONY: up down stop start logs ps build restart shell-backend shell-frontend

up:
	docker compose up --build -d

down:
	docker compose down

stop:
	docker compose stop

start:
	docker compose start

restart:
	docker compose restart

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
