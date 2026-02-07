VENV_BIN = .\.venv\Scripts

run:
	$(VENV_BIN)\uvicorn app.main:app --reload

install:
	$(VENV_BIN)\pip install -r requirements.txt

db-migrate:
	$(VENV_BIN)\alembic revision --autogenerate -m "$(msg)"
	$(VENV_BIN)\alembic upgrade head

db-rollback:
	$(VENV_BIN)\alembic downgrade -1

db-upgrade:
	$(VENV_BIN)\alembic upgrade +1

test:
	$(VENV_BIN)\python -m pytest tests/