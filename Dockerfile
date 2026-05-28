# Stage 1: Build virtual environment
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime image
FROM python:3.11-slim AS runner

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy source code and files
COPY . .

# Set environment defaults
ENV PORT=8080
ENV HOST=0.0.0.0

EXPOSE 8080

# Command to execute FastAPI server in production
CMD ["sh", "-c", "uvicorn app.main:app --host $HOST --port $PORT"]
