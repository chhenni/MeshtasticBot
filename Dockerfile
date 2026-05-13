FROM python:3.12-slim

WORKDIR /app

# Install system dependencies required for serial and BLE support
RUN apt-get update && apt-get install -y --no-install-recommends \
    bluez \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py weather.py ./

# Mount config.yaml at runtime via -v ./config.yaml:/app/config.yaml
# Serial: pass device with --device /dev/ttyUSB0
# TCP:    no extra flags needed
CMD ["python", "main.py"]
