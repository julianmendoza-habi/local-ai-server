# local-ai-server

Stateful AI gateway over a local [Ollama](https://ollama.ai) instance — built with FastAPI, LangChain, and async Python.

A Postman/Newman collection covering all endpoints is included at `local-ai-server.postman_collection.json` — see [Running Tests](#running-tests) for full usage.

## Features

- **Multi-model support** — select a model per request or use the configured default
- **Chat sessions** — stateful conversations with persistent context (in-memory, DB-ready interface)
- **Thinking / non-thinking modes** — maps to Ollama's native `think` parameter
- **Concurrency control** — semaphore-based queue; configurable max concurrent requests and queue depth
- **Streaming** — SSE endpoint for token-by-token streaming
- **Context truncation** — sliding window keeps sessions within model context limits
- **Structured logging** — queue wait time, LLM time, and model per request

---

## Requirements

- Python 3.11+
- [Ollama](https://ollama.ai) running locally
- At least one model pulled: `ollama pull gemma4:e2b`

---

## Setup

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

### `GET /chat/{chat_id}/stream?message=...&mode=...`

Stream tokens via Server-Sent Events. Each event:
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

### Stream a response
```bash
curl -s -N "http://localhost:8000/chat/$CHAT_ID/stream?message=Summarise+that&mode=nothinking"
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

The collection at `local-ai-server.postman_collection.json` exercises every endpoint with a real Ollama instance. It is meant to run in folder order — session IDs are chained via collection variables between folders.

**Install Newman once:**
```bash
npm install -g newman
```

**Run the full collection:**
```bash
newman run local-ai-server.postman_collection.json \
  --timeout-request 180000 \
  --delay-request 500
```

- `--timeout-request 180000` — gives each request up to 3 minutes; LLM calls can be slow, and the SSE stream tests need to wait for the final `done` event.
- `--delay-request 500` — adds 500 ms between requests to avoid hammering the concurrency queue.

**Optional: HTML report**
```bash
npm install -g newman-reporter-htmlextra
newman run local-ai-server.postman_collection.json \
  --timeout-request 180000 \
  --delay-request 500 \
  --reporters cli,htmlextra \
  --reporter-htmlextra-export report.html
```

**What to expect from a passing run:**

```
┌─────────────────────────┬───────────────────┬───────────────────┐
│                         │          executed │            failed │
├─────────────────────────┼───────────────────┼───────────────────┤
│              iterations │                 1 │                 0 │
│                requests │                20 │                 0 │
│            test-scripts │                20 │                 0 │
│              assertions │                40 │                 0 │
└─────────────────────────┴───────────────────┴───────────────────┘
```

Total wall-clock time will be roughly 2–5 minutes depending on model speed. Average response time for LLM calls is in the range of 5–45 seconds; the health check and error-path requests respond in milliseconds.

**Models used by the collection**

The collection has two model-related variables:

| Variable | Default | Purpose |
|---|---|---|
| `allowedModel` | `gemma4:e2b` | Used in the "explicit model" test. Must be a model present in your `ALLOWED_MODELS`. |
| `disallowedModel` | `gpt-99` | Used in the 400-rejection test. Intentionally not a real model name; will always be rejected. |

If your `.env` lists only one model (e.g. `ALLOWED_MODELS=["gemma4:e2b"]`), **no tests will fail** because of it. The `allowedModel` variable already points to that model, and `disallowedModel` (`gpt-99`) is never in any allowed list regardless of your config.

If you want to override `allowedModel` at run time without editing the collection file:
```bash
newman run local-ai-server.postman_collection.json \
  --timeout-request 180000 \
  --delay-request 500 \
  --env-var "allowedModel=llama3"
```

---

## Project Structure

```
src/app/
├── main.py            # FastAPI app, lifespan, exception handlers
├── config.py          # Settings (pydantic-settings + .env)
├── models.py          # Pydantic request/response schemas
├── exceptions.py      # QueueOverloadError + handler
├── session_store.py   # ChatSession dataclass + async SessionStore
├── model_registry.py  # ChatOllama cache + semaphore concurrency
└── routers/
    ├── chat.py        # POST /chat, GET /chat/{id}, DELETE /chat/{id}
    └── streaming.py   # GET /chat/{id}/stream (SSE)
```

---

## Architecture Notes

- **No LangChain memory abstractions** — messages are stored as a plain `list[BaseMessage]` on each session. This makes truncation trivial and the store DB-portable.
- **`ChatOllama` is instantiated once per model name** and reused across all requests (it's stateless).
- **`asyncio.Semaphore`** gates Ollama calls without threads or a separate worker process.
- **Thinking mode** passes `reasoning=True/False` at invocation time, so the same cached model instance handles both modes.
