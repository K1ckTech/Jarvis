FROM python:3.11-slim

WORKDIR /app

# Install system dependencies required for some packages (like soundfile, psycopg)
RUN apt-get update && apt-get install -y \
    libsndfile1 \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install --with-deps chromium

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
