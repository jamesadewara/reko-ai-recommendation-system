# Local Installation Guide

Follow these steps to run the Reko AI Recommendation System locally.

## Prerequisites
- **Python 3.11+**
- **Docker & Docker Compose** (for MongoDB & RabbitMQ)

## Step-by-Step Setup

1. **Clone the repository:**
   ```bash
   git clone <repo>
   cd reko-ai-recommendation-system
   ```

2. **Setup Environment Variables:**
   ```bash
   cp .env.example .env
   ```
   Open `.env` and fill in:
   - `TAVILY_API_KEY`
   - `DEEPSEEK_API_KEY`
   - `GROQ_API_KEY`

3. **Install Dependencies:**
   ```bash
   python -m pip install -r requirements.txt
   ```

4. **Download ML Models:**
   ```bash
   python -m spacy download en_core_web_md
   ```

5. **Start Infrastructure (MongoDB & RabbitMQ):**
   ```bash
   docker-compose up -d mongo rabbitmq
   ```

6. **Seed Initial Data:**
   ```bash
   python scripts/seed_items.py --confirm
   python scripts/build_faiss.py
   ```

7. **Run the Application:**
   ```bash
   uvicorn app.main:app --reload
   taskiq worker app.core.broker:broker
   ```

## Running Tests
Run the integration scripts to verify tasks A and B:
```bash
python scripts/test_task_a.py
python scripts/test_task_b.py
python scripts/test_full_flow.py
```

## Docker Deployment
To run the entire backend via Docker (excluding auth frontend):
```bash
docker-compose up --build -d
```