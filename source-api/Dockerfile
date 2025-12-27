FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    librdkafka-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code from src/ folder
COPY src/ /app/

EXPOSE 8000

# Run the application (main.py is now in /app/)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
