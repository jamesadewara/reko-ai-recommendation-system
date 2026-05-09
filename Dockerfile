FROM python:3.11-slim

WORKDIR /app

# System deps for FAISS, spaCy, and build tools
RUN apt-get update && apt-get install -y \
    gcc g++ libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download spaCy model
RUN python -m spacy download en_core_web_md

# Copy app code
COPY app/ ./app/
COPY scripts/ ./scripts/

# Create localstorage dir
RUN mkdir -p /app/localstorage
RUN mkdir -p /app/models

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
