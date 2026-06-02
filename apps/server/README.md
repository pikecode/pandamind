# PandaMind Server

PandaMind backend — AI model gateway with unified Provider abstraction, prompt templates, and OpenAI-compatible API.

## Quick Start

### Local Development

```bash
# 1. Install dependencies
uv sync

# 2. Create env file and generate a master key
cp .env.example .env
# Edit .env — set ENCRYPTION_KEY:
python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"

# 3. Start PostgreSQL (local or via docker-compose)
docker compose -f ../../docker-compose.dev.yml up -d

# 4. Run migrations
PYTHONPATH=src uv run alembic upgrade head

# 5. Start the server
PYTHONPATH=src uv run uvicorn pandamind.main:app --reload
```

Swagger docs: http://localhost:8000/docs

### Docker (Production)

```bash
cd ../..
# Create .env with ENCRYPTION_KEY set
docker compose up -d
# UI available at http://localhost:80
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | `postgresql://pandamind:pandamind@localhost:5432/pandamind` | PostgreSQL DSN |
| `ENCRYPTION_KEY` | **Yes** | — | Base64-encoded 32-byte key for AES-256-GCM (API key encryption) |
| `AUTH_DISABLED` | No | `true` | Set `false` to enable JWT login |
| `AUTH_USERNAME` | No | `admin` | Login username (when auth enabled) |
| `AUTH_PASSWORD` | No | `changeme` | Login password (when auth enabled) |
| `JWT_SECRET` | No | falls back to `ENCRYPTION_KEY` | HS256 secret for JWT signing |
| `ALLOWED_ORIGINS` | No | `http://localhost:5173,http://localhost:8000` | CORS allowed origins (comma-separated) |
| `LOG_LEVEL` | No | `INFO` | `DEBUG`, `INFO`, `WARNING`, or `ERROR` |
| `HOST` | No | `0.0.0.0` | Bind address |
| `PORT` | No | `8000` | Bind port |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/v1/auth/login` | Login, returns JWT |
| `GET` | `/v1/models` | List model configs |
| `POST` | `/v1/models` | Create model config |
| `GET` | `/v1/models/{id}` | Get model config |
| `DELETE` | `/v1/models/{id}` | Delete model config |
| `GET` | `/v1/models/{id}/ping` | Ping provider health |
| `POST` | `/v1/chat/completions` | OpenAI-compatible chat (SSE streaming) |
| `DELETE` | `/v1/chat/{stream_id}` | Abort a streaming response |
| `GET` | `/v1/chat/stats` | Usage statistics (by model/date) |
| `GET` | `/v1/prompts` | List prompts (filter: `?tag=`, `?search=`) |
| `POST` | `/v1/prompts` | Create prompt |
| `GET` | `/v1/prompts/{id}` | Get prompt |
| `PUT` | `/v1/prompts/{id}` | Update prompt (creates version snapshot) |
| `DELETE` | `/v1/prompts/{id}` | Delete prompt |
| `POST` | `/v1/prompts/{id}/render` | Render prompt with variable substitution |
| `GET` | `/v1/prompts/{id}/versions` | List version history |
| `POST` | `/v1/prompts/{id}/rollback/{version}` | Rollback to a previous version |

## Running Tests

```bash
PYTHONPATH=src uv run pytest tests/ -v
```

## Project Structure

```
apps/server/
├── src/pandamind/
│   ├── main.py              # FastAPI app, middleware, error handlers
│   ├── api/                 # Route handlers (models, chat, prompts, auth)
│   ├── core/                # Config, auth, exceptions, logging, middleware
│   ├── db/                  # SQLAlchemy models, session, seed data
│   ├── providers/           # Ollama + OpenAI-compatible providers, registry
│   └── services/            # KeyManager (AES-256), PromptEngine
├── alembic/                 # Database migrations
├── tests/                   # Unit tests (pytest)
└── pyproject.toml
```
