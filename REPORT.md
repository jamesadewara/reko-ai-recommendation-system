# Project Report: Reko AI Recommendation System

## 1. Executive Summary
The **Reko AI Recommendation System** is a high-performance microservice specialized in delivering real-time, AI-driven product suggestions and managing interactive user conversations. It acts as the "intelligence layer" of the Reko ecosystem, processing user behavior and system events to provide a personalized experience.

## 2. What the Project Does
The system is responsible for the interactive and personalized aspects of the platform:

*   **Real-Time Chat Interface**: Provides a low-latency, WebSocket-based chat system where users can interact with the AI.
*   **Conversation Persistence**: Securely stores all user chat history in a non-relational database (MongoDB) for long-term memory and context.
*   **Contextual Recommendations**: Analyzes user interactions and profile data (synchronized with the Auth System) to suggest relevant products and content.
*   **Event-Driven Personalization**: Responds to system-wide events, such as user birthdays, to trigger special recommendation modes and engagement activities.
*   **Secure Service Integration**: Validates user identities using asymmetric encryption keys (RS256) shared by the Auth System, ensuring that only authenticated users can access personalized data.

## 3. Tools and Technologies Used
The recommendation system uses a specialized stack optimized for real-time data and unstructured content.

### **FastAPI**
*   **What it is**: A modern, high-performance web framework for Python.
*   **Why it was used**: Its native support for WebSockets and asynchronous operations makes it ideal for real-time chat and high-concurrency recommendation requests.

### **MongoDB & Beanie**
*   **What they are**: A NoSQL database and an Object-Document Mapper (ODM).
*   **Why they were used**: Chat history and recommendation metadata are inherently unstructured. MongoDB provides the flexibility needed for these data types, while Beanie adds type safety and structure in Python.

### **Pymongo 4.16+ (Async)**
*   **What it is**: The official Python driver for MongoDB.
*   **Why it was used**: We leverage the latest asynchronous capabilities of Pymongo to ensure non-blocking database operations, maximizing the throughput of the service.

### **Taskiq & RabbitMQ**
*   **What they are**: An asynchronous task queue and message broker.
*   **Why they were used**: To process complex recommendation algorithms and respond to system events in the background, keeping the user-facing API fast and responsive.

### **Hybrid RS256 Verification**
*   **What it is**: A security pattern using both local RSA public keys and remote JWKS (JSON Web Key Sets).
*   **Why it was used**: It allows the system to verify user tokens locally for maximum speed (zero network latency) while still having a fallback to the Auth System for automatic key rotation and resilience.

## 4. Approach & Architecture Decisions
The architecture was designed to be both resilient and highly performant:

### **"Schema-less" Chat Storage**
We opted for MongoDB over a traditional SQL database for chat sessions.
*   **Reasoning**: Conversation structures often evolve (adding AI metadata, sentiment scores, etc.). NoSQL allows us to iterate on the chat features without complex database migrations.

### **Asymmetric Security (Zero-Shared-Secrets)**
The system never sees the user's password. It only receives a cryptographically signed token.
*   **Reasoning**: By using the public key from the Auth System, the Recommendation System can verify a user's identity independently. This "zero-shared-secret" architecture means that even if this service is compromised, the primary user credentials remain safe in the Auth System.

### **Stateful WebSocket Management**
We implemented a custom connection manager to track active WebSocket sessions.
*   **Reasoning**: Real-time applications require careful management of connections to ensure messages are delivered only to the correct, authenticated user while gracefully handling disconnections.

---

## 5. Future Work
Key areas for future development include:

1.  **Vector Search Integration**: Implementing vector databases (like Milvus or Qdrant) to enable advanced similarity searches for product recommendations based on embeddings.
2.  **Streaming AI Responses**: Updating the WebSocket protocol to support token-by-token streaming from Large Language Models (LLMs) for a more "natural" chat experience.
3.  **Cross-Service Caching**: Implementing a Redis layer to cache recommendation results for frequently accessed user profiles.
4.  **Advanced Sentiment Analysis**: Integrating NLP models to analyze chat history in real-time, allowing the recommendation engine to adapt to the user's current mood or intent.

---

## 6. Conclusion
The Reko AI Recommendation System provides a robust, scalable, and secure foundation for the platform's personalized features. By combining the speed of FastAPI with the flexibility of MongoDB and the security of RS256, it delivers a state-of-the-art user experience that is both fast and trustworthy.
