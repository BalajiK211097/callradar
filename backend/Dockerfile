FROM python:3.12-slim

WORKDIR /app

# Build context is the repo root so we can pull in both backend/ and pipeline/
COPY pipeline/requirements.txt ./pipeline/requirements.txt
COPY backend/requirements.txt ./backend/requirements.txt

RUN pip install --no-cache-dir -r pipeline/requirements.txt \
 && pip install --no-cache-dir -r backend/requirements.txt

COPY pipeline/ ./pipeline/
COPY backend/ ./backend/

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
