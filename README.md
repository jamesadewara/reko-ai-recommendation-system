# Reko AI Recommendation System

A high-performance microservice dedicated to product analysis, user preferences, and real-time AI-driven recommendations. This service also manages user chat history and provides a WebSocket-based chat interface.

---

## Overview

The **Reko AI Recommendation System** focuses on:
- **AI Recommendations**: Personalized product and content suggestions.
- **Chat History**: Persistent storage of user conversations in MongoDB.
- **Real-time Chat**: WebSocket-based interface for low-latency interactions.
- **Birthday Events**: Responds to user birthdays by providing special celebratory recommendations.

---

## Features

✅ **AI & Recommendations**
- Personalized recommendation engine integration.
- Context-aware suggestions based on user behavior.
- Special "Birthday Mode" recommendations triggered via RabbitMQ.

✅ **Chat System**
- Persistent chat sessions stored in MongoDB.
- REST API for chat management (List, Create, Rename, Delete).
- Real-time WebSocket connection for active chatting.
- Message history tracking.

✅ **Inter-Service Integration**
- **Hybrid Token Verification**: Supports both local RSA public keys (RS2A) for high performance and remote JWKS for automatic key rotation.
- **X-Internal-Secret**: Secure header-based verification for trusted service-to-service calls.
- **RabbitMQ Integration**: Listens for system-wide events (like birthdays) to trigger background tasks.
- **Taskiq Orchestration**: Robust background task management using RabbitMQ (No Redis).

---

## Project Structure

```
├── app/
│   ├── main.py                 # FastAPI application & lifespan
│   ├── core/
│   │   ├── config.py           # Settings (MongoDB, RabbitMQ, JWT, AI Keys)
│   │   ├── broker.py           # Taskiq broker (RabbitMQ)
│   │   ├── connections.py      # WebSocket connection manager
│   │   ├── security.py         # RS2A, JWKS & internal secret verification
│   │   └── session.py          # MongoDB (Pymongo 4.16+) initialization
│   ├── api/
│   │   └── v1/
│   │       └── endpoints/
│   │           ├── chats.py    # REST API for chat management
│   │           └── websocket.py # Real-time chat handler
│   ├── documents/
│   │   ├── chat.py             # ChatSession Document
│   │   ├── user.py             # UserDocument (Style Fingerprint, Taste Profile)
│   │   ├── temp_model.py       # TempModelDocument (Pre-onboarding profiles)
│   │   ├── item.py             # ItemDocument (Movies, Food, Products)
│   │   └── review.py           # ReviewDocument (AI Generated Reviews)
│   └── tasks/
│       └── birthday.py         # Birthday event listener
├── requirements.txt            # Python dependencies
├── .env.example                # Configuration template
└── README.md
```

---

## Installation & Setup

### Prerequisites
- Python 3.11+
- MongoDB 6.0+
- RabbitMQ 3.12+

### Setup
1. **Clone & Install**:
   ```bash
   pip install -r requirements.txt
   ```
2. **Configure**:
   Copy `.env.example` to `.env` and set your `DATABASE_URL` (MongoDB) and `RABBITMQ_URL`.
3. **Run**:
   ```bash
   uvicorn app.main:app --reload --port 8001
   ```

---

## API Endpoints

### Chat REST API
- `GET /api/v1/chats/`: List all chat sessions.
- `POST /api/v1/chats/`: Start a new chat.
- `PATCH /api/v1/chats/{id}`: Rename a chat.
- `DELETE /api/v1/chats/{id}`: Delete a chat.

### WebSocket
- `WS /api/v1/ws/chat/{chat_id}?token={JWT}`: Real-time chat connection.

---

## Background Tasks

This service runs a **Taskiq Worker** listening to RabbitMQ:
- **`handle_birthday_event`**: Triggered by the Auth System. Prepares birthday-themed recommendations for the user.

To run the worker:
```bash
taskiq worker app.core.broker:broker
```
