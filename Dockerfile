# Finsight production image. Used by Railway.
FROM python:3.12-slim

# System deps needed by pdfplumber (for PDFs with embedded images) and pikepdf.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libqpdf-dev \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first so Docker can cache this layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code.
COPY app/ ./app/

# Create the data directory for SQLite + uploaded PDFs.
# Railway will mount a persistent volume here so this survives redeploys.
RUN mkdir -p /app/data/uploads

# Railway sets the PORT env var at runtime. We default to 8000 for local docker runs.
ENV PORT=8000
EXPOSE 8000

# Start the app. Note: no --reload in production. One worker is fine for a personal app.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}