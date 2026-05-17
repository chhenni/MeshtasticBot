# ── Stage 1: builder — install deps, copy source, run tests ──────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    bluez \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY tests/ tests/
COPY conftest.py .

RUN python -m pytest tests/ -q --tb=short

# ── Stage 2: runtime — lean image with only the application ──────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    bluez \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --from=builder /app/src/ src/

# Mount config.yaml at runtime via -v ./config.yaml:/app/config.yaml
# Serial: pass device with --device /dev/ttyUSB0
# TCP:    no extra flags needed
CMD ["python", "src/main.py"]
