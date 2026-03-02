FROM python:3.11-slim

RUN pip install --no-cache-dir "celery[redis]>=5.4"

WORKDIR /app
COPY tasks.py .

CMD ["celery", "-A", "tasks", "worker", "--loglevel=info", "--events", "-Q", "celery"]
