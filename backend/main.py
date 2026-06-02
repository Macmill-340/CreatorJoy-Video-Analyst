import json
import os
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select
from pydantic import BaseModel

from backend.database import create_db_and_table, seed_initial_data, get_session, User, VideoMetadata
from backend.auth import get_password_hash, verify_password, create_access_token, get_current_user, UserContext
from agent.rag import process_video
from agent.agent import run_agent, run_planner_executor, build_critic_prompt, async_llm


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_table()
    seed_initial_data()
    yield


app = FastAPI(title="CreatorJoy Video Analyst API", lifespan=lifespan)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Required so the React frontend can call the API cross-origin in dev.
#
# Note: the combination of allow_origins=["*"] + allow_credentials=True is a
# CORS spec violation — browsers reject credentialed requests against a wildcard
# origin. We don't use cookies (Bearer tokens only) so it wouldn't bite us, but
# a reviewer will flag it. Driving from env var means dev defaults are safe and
# production explicitly opts in to its frontend origin.
cors_origins_env = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
)
allow_origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/register")
def register_user(username: str, password: str, tenant_id: int, role: str = "staff",
                  session: Session = Depends(get_session)):
    existing = session.exec(select(User).where(User.username == username)).first()
    if existing:
        raise HTTPException(status_code=400, detail="User already registered")
    new_user = User(username=username, password_hash=get_password_hash(password), role=role, tenant_id=tenant_id)
    session.add(new_user)
    session.commit()
    return {"message": "User created successfully"}


@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.username == form_data.username)).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role, "tenant_id": user.tenant_id}
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/me")
def get_me(current_user: UserContext = Depends(get_current_user)):
    return current_user


class VideoRequest(BaseModel):
    url1: str  # becomes Video A
    url2: str  # becomes Video B


@app.post("/analyze_videos")
def analyze_videos(request: VideoRequest, current_user: UserContext = Depends(get_current_user)):
    """
    Processes two videos (YouTube or Instagram).
    url1 → Video A, url2 → Video B.
    video_label is stored in both ChromaDB and SQLite for citation and comparison.
    """
    res1 = process_video(request.url1, current_user.tenant_id, video_label="A")
    res2 = process_video(request.url2, current_user.tenant_id, video_label="B")

    if "error" in res1:
        raise HTTPException(status_code=400, detail=f"Error Video A: {res1['error']}")
    if "error" in res2:
        raise HTTPException(status_code=400, detail=f"Error Video B: {res2['error']}")

    return {"message": "Both videos analyzed and added to the Knowledge Base."}


class ChatRequest(BaseModel):
    message: str
    history: str = ""


@app.post("/chat")
def chat(request: ChatRequest, current_user: UserContext = Depends(get_current_user)):
    """Synchronous chat — kept for Streamlit fallback."""
    try:
        response = run_agent(request.message, request.history, current_user.tenant_id)
        return {"reply": response}
    except Exception as e:
        # Surface upstream LLM errors as readable 502s instead of opaque 500s.
        raise HTTPException(status_code=502, detail=f"Agent error: {type(e).__name__}: {e}")


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest, current_user: UserContext = Depends(get_current_user)):
    """
    Streaming chat via Server-Sent Events.

    Architecture:
    1. run_planner_executor() — synchronous, fast (one LLM call for intent classification)
    2. build_critic_prompt() — pure function, no IO
    3. async_llm.astream() — streams tokens as they arrive from Gemini
    4. Each token yielded as SSE: data: {"token": "..."}\\n\\n
    5. Final event: data: [DONE]\\n\\n

    Frontend consumes with: const reader = response.body.getReader()
    """
    state = run_planner_executor(request.message, request.history, current_user.tenant_id)
    prompt = build_critic_prompt(state)

    async def generate():
        try:
            async for chunk in async_llm.astream(prompt):
                token = chunk.content
                if token:
                    yield f"data: {json.dumps({'token': token})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering if behind a proxy
        }
    )


@app.get("/videos")
def get_videos(current_user: UserContext = Depends(get_current_user), session: Session = Depends(get_session)):
    videos = session.exec(
        select(VideoMetadata).where(VideoMetadata.tenant_id == current_user.tenant_id)
    ).all()
    return videos
