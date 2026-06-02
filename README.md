# CreatorJoy — YouTube & Instagram Reels Video Analyst

A multi-tenant AI agent that ingests two short-form videos (YouTube or Instagram Reels), pulls metadata + transcript + engagement metrics, and lets you chat with the results. Responses stream live and include source citations like `[Video A, Chunk 2]`.

## Tech stack (and why)

| Layer        | Choice                                | Reason                                                                 |
|--------------|---------------------------------------|------------------------------------------------------------------------|
| API          | FastAPI + Uvicorn                     | Async support out of the box, native SSE via StreamingResponse         |
| Auth         | JWT (PyJWT) + bcrypt + SQLModel       | Stateless, tenant scoped, no session table to maintain                 |
| DB           | SQLite via SQLModel                   | Zero ops for the demo, swap to Postgres by changing one URL            |
| Vector store | ChromaDB (local persist)              | No managed service required, can migrate to Pinecone/Qdrant at scale   |
| Embeddings   | HuggingFace all-MiniLM-L6-v2          | 384-dim, fast, runs on CPU                                             |
| Agent        | LangGraph (planner → executor → critic) | Explicit state machine, each node is independently testable           |
| LLM          | Gemini 2.0 Flash Lite                 | ~$0.075/1M input tokens — 200x cheaper than GPT-4o for this workload   |
| YT transcripts | yt-dlp signed CDN subtitle URLs     | youtube-transcript-api now throws PoTokenRequired on servers           |
| IG transcripts | faster-whisper `base` int8          | 4x faster than openai-whisper on CPU, same model weights               |
| Frontend     | Vite + React + Tailwind               | Sub-100ms HMR, static build, no SSR overhead for a chat SPA            |
| Streaming    | Server-Sent Events                    | Browser-native, no WebSocket handshake, simple to reconnect            |

## Architecture

```
   ┌─────────────┐
   │   Browser   │  ← React + SSE consumer
   └──────┬──────┘
          │ /api/* (proxied by Vite)
          ▼
   ┌─────────────┐
   │   FastAPI   │
   ├─────────────┤
   │ /analyze    │──→ yt-dlp ──→ (YouTube subs) OR (faster-whisper)
   │             │           │
   │             │           ▼
   │             │    ChromaDB  +  SQLite (VideoMetadata)
   │             │
   │ /chat       │──→ LangGraph: planner → executor → critic
   │ /chat/stream│        │
   │             │        └──→ Gemini 2.0 Flash Lite (streaming for /stream)
   └─────────────┘
```

## Setup

### 1. Backend

```bash
# from project root
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Required system dependency for Instagram transcription:
#   Linux: sudo apt install ffmpeg
#   Mac:   brew install ffmpeg
#   Win:   download from ffmpeg.org and add to PATH

cp .env.example .env
# fill in GEMINI_API_KEY and pick a long random SECRET_ENV_KEY

uvicorn backend.main:app --reload --port 8000
```

Backend listens on http://localhost:8000. Default credentials: `admin` / `admin123`.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Opens at http://localhost:5173. Vite proxies `/api/*` to the FastAPI backend, so no CORS issues in dev.

### 3. Run both for the demo

- Terminal 1: `uvicorn backend.main:app --reload --port 8000`
- Terminal 2: `cd frontend && npm run dev`
- Open http://localhost:5173

## Fresh start

The SQLite schema and vector store are recreated on first run. If you change `VideoMetadata` columns or want to wipe analyzed videos:

```bash
rm -f assistant.db
rm -rf chroma_db/
```

Then restart the backend — `create_db_and_table()` rebuilds everything.

## Known limitations

- **Instagram follower count** isn't always exposed by yt-dlp without an authenticated session — `subs` may be `0` for some reels.
- **Whisper cold start** — first Instagram analysis triggers a ~30s model download to `~/.cache/huggingface/hub/`. Subsequent calls reuse it.
- **Streamlit version** (`app.py`) is kept for internal tooling. It talks to `/chat` (non-streaming) and was used for early dev. The React app is the demo target.

## Scalability and cost (1000 creators/day target)

**Per-video cost today:**
- yt-dlp + ChromaDB + Whisper (CPU): zero marginal $
- Gemini 2.0 Flash Lite at ~3K input tokens per analysis: ≈ $0.0001
- Chat turn at ~2K tokens: ≈ $0.00007

**At 1000 creators × 2 videos × ~5 chat turns:**
- 2000 ingestions, 10,000 chat turns → roughly $1-5/day in Gemini spend.
- Whisper on a single CPU worker would saturate. The right move at scale is one of:
  - Self-hosted faster-whisper on a small GPU (T4 or better) — handles ~20x throughput
  - AssemblyAI batch transcription at ~$0.01/reel — no infra to manage
- ChromaDB local will hit IO limits past ~10M chunks. Migrate to Qdrant Cloud (~$70/mo) or Pinecone.
- Use Celery + Redis for an ingestion queue so user-facing latency stays low; cache by video URL/ID to skip duplicate ingestion.

**Why not the alternatives:**
- OpenAI Whisper API ($0.006/min) → 100% more expensive than self-hosted faster-whisper.
- GPT-4o ($15/1M tokens) → 200x more expensive than Gemini Flash Lite for the same routing+RAG.
- Pinecone from day one → unnecessary $70/mo while ChromaDB still fits.

## File layout

```
.
├── backend/             FastAPI + auth + SQLModel schema
│   ├── main.py          /login, /analyze_videos, /chat, /chat/stream, /videos
│   ├── auth.py          JWT + bcrypt
│   └── database.py      Tenant, User, VideoMetadata, AgentTrace
├── agent/               LangGraph + RAG
│   ├── agent.py         planner → executor → critic, streaming helpers
│   └── rag.py           yt-dlp ingestion, Whisper, ChromaDB
├── frontend/            Vite + React + Tailwind
│   ├── vite.config.js   /api proxy → :8000
│   └── src/
│       ├── App.jsx
│       └── components/  LoginScreen, VideoPanel, ChatPanel
├── app.py               Legacy Streamlit client (talks to /chat, no streaming)
├── requirements.txt
├── .env.example
└── README.md
```
