# local-ai-server

Stateful AI gateway over a local [Ollama](https://ollama.ai) instance — built with FastAPI, LangChain, and async Python.

Three Postman/Newman collections are included — see [Running Tests](#running-tests) for full usage.

## Features

- **Multi-model support** — select a model per request or use the configured default
- **Chat sessions** — stateful conversations backed by PostgreSQL (falls back to in-memory without `DATABASE_URL`)
- **Thinking / non-thinking modes** — maps to Ollama's native `think` parameter
- **Concurrency control** — semaphore-based queue; configurable max concurrent requests and queue depth
- **Streaming** — SSE endpoint for token-by-token streaming
- **Context truncation** — sliding window keeps sessions within model context limits
- **Structured logging** — queue wait time, LLM time, and model per request

---

## Docker (recommended)

Everything runs in Docker: the API server, PostgreSQL, and Ollama. Pick the compose file that matches your hardware.

### NVIDIA GPU

> **Prerequisite:** [`nvidia-container-toolkit`](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) must be installed and configured on the host.

```bash
cp .env.example .env  # adjust models if needed

docker compose -f docker-compose.yml -f docker-compose.nvidia.yml up -d
```

### AMD GPU (ROCm)

> **Prerequisite:** ROCm drivers installed on the host.

```bash
cp .env.example .env

docker compose -f docker-compose.yml -f docker-compose.amd.yml up -d
```

### CPU only

No extra prerequisites — runs Ollama on CPU.

```bash
cp .env.example .env

docker compose up -d
```

Models listed in `ALLOWED_MODELS` (in `.env`) are pulled automatically on first start. Check progress with:

```bash
docker compose logs -f ollama
```

The API is then available at `http://localhost:8000`.

### Stopping

```bash
docker compose down          # keep volumes (DB + model weights)
docker compose down -v       # also delete volumes
```

---

## Requirements (local dev, no Docker)

- Python 3.11+
- [Ollama](https://ollama.ai) running locally
- At least one model pulled: `ollama pull gemma4:e2b`

---

## Setup (local dev)

```bash
# 1. Clone and enter the repo
cd local-ai-server

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -e ".[dev]"

# 4. Configure (optional)
cp .env.example .env
# Edit .env to match your Ollama setup and available models

# 5. Run the server
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs`

---

## Configuration (`.env`)

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `DEFAULT_MODEL` | `gemma4:e2b` | Fallback model when none specified |
| `ALLOWED_MODELS` | `["gemma4:e2b", "llama3", "mistral"]` | Whitelist of accepted models |
| `MAX_CONCURRENT_OLLAMA_REQUESTS` | `2` | Max simultaneous Ollama calls |
| `MAX_QUEUE_SIZE` | `10` | Max requests waiting before 503 |
| `REQUEST_TIMEOUT_SECONDS` | `120.0` | Abort LLM call after N seconds |
| `MAX_MESSAGES_PER_SESSION` | `20` | Sliding window per chat |
| `OLLAMA_KEEP_ALIVE` | `-1` | Seconds to keep model in VRAM (-1 = forever) |
| `DATABASE_URL` | _(unset)_ | PostgreSQL DSN. If unset, sessions are stored in memory (lost on restart) |

---

## API Reference

### `POST /chat`

Start a new chat or continue an existing one.

**Request body:**
```json
{
  "message": "Why is the sky blue?",
  "chat_id": "optional-existing-id",
  "model": "optional-model-name",
  "mode": "thinking"
}
```

**Response:**
```json
{
  "chat_id": "550e8400-e29b-41d4-a716-446655440000",
  "model": "gemma4:e2b",
  "reply": "The sky appears blue because...",
  "thinking": "Let me reason through this...",
  "messages": [...]
}
```

Model resolution order: `request.model` → `session.model` → `DEFAULT_MODEL`

---

### `GET /chat/{chat_id}`

Retrieve full chat history.

---

### `DELETE /chat/{chat_id}`

Delete a chat session.

---

### `POST /chat/stream`

Create a new session (or continue an existing one) and stream the reply immediately — no separate `POST /chat` needed first.

**Request body** (same schema as `POST /chat`):
```json
{
  "message": "Explain closures briefly.",
  "chat_id": "optional-existing-id",
  "model": "optional-model-name",
  "mode": "nothinking"
}
```

**Response:** SSE stream. The `chat_id` assigned to the new session arrives in the final `done` event:
```
data: {"token": "A"}
data: {"token": " closure"}
...
data: {"done": true, "chat_id": "550e8400-...", "model": "gemma3:4b"}
```

Save the `chat_id` from the `done` event to continue the conversation in subsequent requests.

---

### `GET /chat/{chat_id}/stream?message=...&mode=...`

Stream tokens on an **existing** session via Server-Sent Events. Each event:
```
data: {"token": "sky"}
data: {"token": " appears"}
...
data: {"done": true, "chat_id": "...", "model": "gemma4:e2b"}
```

---

### `GET /health`

Returns `{"status": "ok"}`.

---

## Example `curl` Requests

### New chat (default model)
```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Explain recursion briefly"}' | python3 -m json.tool
```

### New chat with thinking mode
```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is 17 * 38?", "mode": "thinking"}' | python3 -m json.tool
```

### Continue an existing session
```bash
CHAT_ID="<chat_id from previous response>"

curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"Give me a code example\", \"chat_id\": \"$CHAT_ID\"}" | python3 -m json.tool
```

### Use a specific model
```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!", "model": "llama3"}' | python3 -m json.tool
```

### Stream a response — new session (first message streams immediately)
```bash
curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "Explain closures briefly."}'
# Save the chat_id from the done event, then continue:
curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"Give me a Python example.\", \"chat_id\": \"$CHAT_ID\"}"
```

### Stream a response — existing session (GET)
```bash
curl -N "http://localhost:8000/chat/$CHAT_ID/stream?message=Summarise+that&mode=nothinking"
```

### Get chat history
```bash
curl -s http://localhost:8000/chat/$CHAT_ID | python3 -m json.tool
```

### Delete a session
```bash
curl -s -X DELETE http://localhost:8000/chat/$CHAT_ID
```

---

## Running Tests

### Unit / integration tests (no Ollama needed)

The pytest suite mocks the LLM, so it runs offline and is fast.

```bash
pytest -v

# With coverage
pip install pytest-cov
pytest --cov=app --cov-report=term-missing
```

### Newman (end-to-end against a live server)

Three collections are provided. Pick the one that matches your model:

| File | Use when |
|---|---|
| `local-ai-server.postman_collection.json` | Default — models without thinking support (gemma3:4b, gemma4:e2b, etc.) |
| `local-ai-server.nothinking.postman_collection.json` | Same as above, explicitly named |
| `local-ai-server.thinking.postman_collection.json` | Models with thinking support (deepseek-r1, qwq, etc.) |

All collections run in folder order — session IDs are chained via collection variables between folders. They cover `POST /chat`, `GET /chat/stream`, `POST /chat/stream`, history, error paths, and cleanup.

**Install Newman once:**
```bash
npm install -g newman
```

**Run (non-thinking model):**
```bash
newman run local-ai-server.postman_collection.json \
  --timeout-request 180000 \
  --delay-request 500
```

**Run (thinking-capable model):**
```bash
newman run local-ai-server.thinking.postman_collection.json \
  --timeout-request 180000 \
  --delay-request 500 \
  --env-var "allowedModel=deepseek-r1:7b"
```

- `--timeout-request 180000` — gives each request up to 3 minutes; LLM calls and SSE stream tests need to wait for the final `done` event.
- `--delay-request 500` — 500 ms between requests to avoid hammering the concurrency queue.

**Optional: HTML report**
```bash
npm install -g newman-reporter-htmlextra
newman run local-ai-server.postman_collection.json \
  --timeout-request 180000 \
  --delay-request 500 \
  --reporters cli,htmlextra \
  --reporter-htmlextra-export report.html
```

**Overriding collection variables at run time:**
```bash
newman run local-ai-server.postman_collection.json \
  --timeout-request 180000 \
  --delay-request 500 \
  --env-var "allowedModel=gemma4:e2b" \
  --env-var "baseUrl=http://192.168.1.10:8000"
```

---

## Project Structure

```
├── Dockerfile
├── docker-compose.yml          # base: api + postgres + ollama (CPU)
├── docker-compose.nvidia.yml   # override: adds NVIDIA GPU to ollama
├── docker-compose.amd.yml      # override: switches ollama to ROCm image
├── db/
│   └── init.sql                # PostgreSQL schema (sessions, messages, users stub)
├── AUTH_STRATEGY.md            # Options for adding OAuth2 in the future
└── src/app/
    ├── main.py            # FastAPI app, lifespan, exception handlers
    ├── config.py          # Settings (pydantic-settings + .env)
    ├── models.py          # Pydantic request/response schemas
    ├── exceptions.py      # QueueOverloadError + handler
    ├── session_store.py   # SessionStore (in-memory) + PostgresSessionStore
    ├── model_registry.py  # ChatOllama cache + semaphore concurrency
    └── routers/
        ├── chat.py        # POST /chat, GET /chat/{id}, DELETE /chat/{id}
        └── streaming.py   # POST /chat/stream, GET /chat/{id}/stream (SSE)
```

---

## Architecture Notes

- **No LangChain memory abstractions** — messages are stored as a plain `list[BaseMessage]` on each session. This makes truncation trivial and the store DB-portable.
- **`ChatOllama` is instantiated once per model name** and reused across all requests (it's stateless).
- **`asyncio.Semaphore`** gates Ollama calls without threads or a separate worker process.
- **Thinking mode** passes `reasoning=True/False` at invocation time, so the same cached model instance handles both modes.
