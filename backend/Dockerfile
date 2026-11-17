FROM python:3.11-slim
WORKDIR /app

ENV PYTHONIOENCODING=utf-8
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Docker kills ten seconds after asking to stop. Open live streams would keep
# uvicorn waiting past that, so it closes them after five and leaves the rest
# for the app's own shutdown — the bot's worker finishing what is in hand.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "5"]
