# REKO AI — AI-Powered Personalized Recommendation & Review Generation Engine

## Hackathon: DSN X BCT LLM Agent Challenge
### Team: Agentic Engineers

## What It Does
Reko AI is an intelligent recommendation and review engine specifically localized for the Nigerian context. It goes beyond simple collaborative filtering by using Tavily to perform deep web searches on users, feeding their digital footprints into an NLP pipeline (spaCy + LiteLLM) to extract a highly personalized "Taste Profile" and "Style Fingerprint". 

The core engine uses these models to generate hyper-personalized product reviews that sound exactly like the user wrote them, and powers a context-aware ReAct recommendation agent that suggests content based on their exact mood, time of day, location (e.g., Lagos, Abuja), and hybrid similar-user interests.

## Architecture
- **Auth Service** (FastAPI + PostgreSQL) — Authentication layer
- **AI Backend** (FastAPI + MongoDB + FAISS) — Core intelligence layer
- **Frontend** (Next.js) — User interface

## Tech Stack
- **Tavily**: Deep Search Engine
- **DeepSeek + Groq**: LLM Reasoning & Generation
- **spaCy en_core_web_md + Custom EntityRuler**: Natural Language Processing
- **Sentence Transformers + FAISS**: Embeddings & Vector Search
- **Beanie + PyMongo**: NoSQL Database
- **Taskiq + RabbitMQ**: Asynchronous Task Queue

## Quick Start
```bash
git clone <repo>
cd reko-ai-recommendation-system
cp .env.example .env
# Fill in API keys (Tavily, DeepSeek, Groq)
pip install -r requirements.txt
python -m spacy download en_core_web_md
docker-compose up -d mongo rabbitmq
python scripts/seed_items.py --confirm
python scripts/build_faiss.py
uvicorn app.main:app --reload
```

## API Endpoints
- `POST /api/v1/search/deep` — Deep search user profiles
- `POST /api/v1/reviews/generate` — Generate personalized review (Task A)
- `POST /api/v1/recommendations` — Get recommendations with reasoning (Task B)
- `POST /api/v1/ads/recommend` — Business ad recommendations
- `WS /api/v1/ws/chat/{chat_id}` — Real-time streaming chat

## Environment Variables
| Variable | Description |
|---|---|
| DATABASE_URL | MongoDB Connection string |
| RABBITMQ_URL | RabbitMQ Connection string |
| TAVILY_API_KEY | Tavily deep search API key |
| DEEPSEEK_API_KEY | Primary LLM API key |
| GROQ_API_KEY | Fallback LLM API key |
| LITELLM_MODEL_PRIMARY | e.g. deepseek/deepseek-chat |

*(See `.env.example` for the complete list)*

## Nigerian Context
- **EntityRuler** detects: Lagos, Ikeja, Lekki, Surulere, Abuja, Ibadan, Port Harcourt
- **Nigerian markers**: "na so", "abeg", "omo", "no wahala", "how far"
- **Content**: Nollywood movies, Afrobeats, Jollof, Suya, Amala

## License
APACHE 2.0 LICENSE
