## Project Report: REKO AI
### Hackathon: DSN X BCT LLM Agent Challenge

### Task A: User Modeling (Review Generation)
*   **Hackathon Requirement**: Simulate star ratings and written reviews for unseen items while capturing tone, rating behaviour, and contextual nuance.
*   **Approach:** We used Tavily to perform a deep web search retrieving a user's GitHub activity and web mentions. This corpus is parsed by spaCy to extract a structural "Style Fingerprint" (vocabulary richness, punctuation habits, slang). We then use LiteLLM (DeepSeek) to extract a "Taste Profile". 
*   **Rating:** The predicted rating is calculated via cosine similarity between the user's encoded interests and the product's embedding.
*   **Evaluation:** BERTScore evaluates the authenticity of the generated review against the user's raw corpus.
*   **Results:** Achieved highly personalized reviews that structurally mimic the user's specific online communication style, complete with Nigerian localized slang where applicable.

### Task B: Recommendation Engine
*   **Hackathon Requirement**: Rank and recommend items tailored to individual user context, handling cold-start, cross-domain, and multiturn scenarios via agentic workflows.
*   **Approach:** Implemented a FAISS vector index combined with Chain-of-Thought (CoT) reasoning, ReAct filtering, and hybrid matching.
*   **Reasoning:** DeepSeek generates a step-by-step justification detailing why specific recommendations were made based on the user's traits and current context (e.g., mood, time of day).
*   **Filtering:** A logical ReAct agent adjusts scores or outright excludes items that clash with the context (e.g., avoiding 3-hour movies when the user is tired).
*   **Results:** Blazing-fast similarity retrieval enriched by thoughtful, context-aware AI reasoning logic.

### Nigerian Contextualization (Bonus Objective)
*   **Hackathon Requirement**: Additional marks if contextualized to behave and sound like Nigerians.
*   **Implementation:**
    - Developed a custom spaCy `EntityRuler` pre-loaded with Nigerian locations (Lagos, Ikeja, Abuja).
    - Included a robust set of Nigerian content in the item catalog (Nollywood, Afrobeats, local cuisine).
    - Instructed the LLM pipelines to prioritize Pidgin markers (abeg, omo, na so) when the user's profile indicates Nigerian heritage.

### Architecture Decisions
- **Why Tavily over scraping:** Reliable, avoids CAPTCHAs, legal, and extremely fast for consolidating identity footprints.
- **Why DeepSeek → Groq:** DeepSeek offers the best cost-to-reasoning ratio for primary generation, while Groq provides near-instant fallback generation to ensure 100% uptime.
- **Why FAISS + sentence-transformers:** Fast, accurate, and requires zero fine-tuning compared to training a two-tower neural network from scratch.

### Challenges & Solutions
- **Handling LLM Downtime:** Addressed via the Tenacity retry decorator and a strict primary/fallback router in LiteLLM.
- **Slow Vector Distance Calculations:** Solved by migrating from manual linear numpy dot-products to an optimized FAISS flat index.

### Future Work
- Fine-tuned GPT-2 or LLaMA per user for even more hyper-specific style imitation (requires GPU infrastructure).
- Full Two-Tower neural model when the dataset grows to >100k reviews.
- Real-time social media streaming via webhooks to update user profiles incrementally.

---

## Approach Overview
Reko AI employs a multi-stage, context-aware artificial intelligence pipeline designed to deeply understand user preferences and cultural nuances. Rather than relying on simple collaborative filtering or rigid demographic boxes, the system autonomously maps a user's digital footprint using deep web search (Tavily). This raw corpus is analyzed using an NLP pipeline (spaCy + LiteLLM) to extract a highly granular `StyleFingerprint` and `TasteProfile`. For recommendations, we utilize a Chain-of-Thought (CoT) reasoning model paired with FAISS vector search and a ReAct agent to ensure that every suggested item is contextually relevant, culturally aligned (e.g., Nigerian colloquialisms), and logically sound.

## Architecture Diagram
*(Insert diagram here showing: Client -> API Gateway -> Auth Service & AI Engine -> MongoDB/RabbitMQ/Taskiq -> FAISS/LLMs)*

## Task A: User Modeling
**Pipeline:** `Tavily Deep Search -> Text Corpus -> spaCy Entity Extraction -> LiteLLM Synthesis -> UserDocument`

To capture the true voice and preference of a user, we chose prompt injection and dynamic context synthesis over costly fine-tuning. Fine-tuning models per user is economically unviable and too slow for a real-time onboarding experience. Instead, we compile a 15,000+ character corpus of the user's public internet activity. Our NLP pipeline scores this corpus for formality, vocabulary richness, and cultural markers. 
To validate the generated reviews, we implemented **BERTScore evaluation**. Instead of relying purely on subjective LLM grading, BERTScore calculates the semantic similarity (F1 score) between the generated review and the user's actual past writing, ensuring authentic voice replication.

## Task B: Recommendation
**Pipeline:** `Context Parsing -> CoT Reasoning -> FAISS Vector Search -> Hybrid Matching -> ReAct Agent Filtering -> Final Output`

We chose FAISS paired with high-dimensional embeddings (SentenceTransformers) over a traditional Two-Tower neural network. This provides comparable quality and sub-millisecond retrieval speeds without the need for massive, static training datasets.
1. **CoT Reasoning:** Before searching, an LLM drafts a logical reasoning chain explaining *why* certain genres or items fit the user's current context (mood, time, location).
2. **FAISS Retrieval:** We retrieve the top 50 semantically similar items based on the user's encoded interests.
3. **Hybrid Matching:** We boost the scores of items liked by users with >85% similar taste profiles.
4. **ReAct Agent:** An autonomous agent evaluates the top candidates, filtering out inappropriate items (e.g., a 3-hour movie for a user who explicitly stated they are "tired").

## Ablation Studies
To mathematically prove our design choices, we conducted ablation studies (removing components to measure the performance drop).
* *Results from `docs/ablation_results.json`*
* **Task A (Voice Authenticity):** Removing the `StyleFingerprint` from the generation prompt resulted in a BERTScore F1 drop from ~0.87 to ~0.62. Removing the Nigerian Context markers resulted in generic outputs completely devoid of cultural colloquialisms.
* **Task B (Recommendation Relevance):** Disabling the CoT reasoning chain reduced human-graded relevance from 4.5/5 to 3.0/5. Disabling the ReAct filtering agent resulted in an average of 3 inappropriate items slipping into the top 10 results under constrained contexts.

## Cost Analysis
Stateless API design and strategic LLM fallbacks keep unit economics extremely low:
* **Tavily (Deep Search):** $0.001/search × 6 queries/user = **$0.006 / user**
* **DeepSeek (Primary LLM):** ~$0.14/M tokens × 2K tokens/user = **$0.0003 / user**
* **Groq (Fallback LLM):** Free tier (Llama 3 70B)
* **Total:** **~$0.01** per user onboarding.

## Scalability
* **Vector Search:** FAISS index operates entirely in RAM and easily scales to handle 1M+ items with sub-millisecond latency.
* **Database:** MongoDB Atlas serverless handles high-throughput document storage and scales elastically.
* **Asynchronous Workers:** Taskiq and RabbitMQ decouple heavy operations (like deep searches and periodic TempModel cleanups), preventing API blockage during traffic spikes.
