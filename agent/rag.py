import re
import json
import os
import tempfile
import requests
import yt_dlp
from typing import Optional, Tuple
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlmodel import Session
from backend.database import VideoMetadata, engine

# ── Embeddings + Vector Store ──────────────────────────────────────────────────
embeddings = HuggingFaceEmbeddings(
    model_name="all-MiniLM-L6-v2",
    encode_kwargs={"normalize_embeddings": True},
)

#set up chroma db for chunking
vector_store = Chroma(
    embedding_function=embeddings,
    persist_directory="./chroma_db",
)


# ── Platform detection ─────────────────────────────────────────────────────────
def detect_platform(url: str) -> str:
    """Returns 'youtube', 'instagram', or raises ValueError."""
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    else:
        raise ValueError(f"Unsupported platform URL: {url}")


def extract_video_id(url: str) -> Optional[str]:
    """Extract 11-char YouTube video ID."""
    pattern = (
        r"(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|"
        r"(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})"
    )
    match = re.search(pattern, url)
    return match.group(1) if match else None


# ── YouTube transcript via yt-dlp subtitle CDN URLs ───────────────────────────
# WHY: youtube-transcript-api throws PoTokenRequired on server environments.
# yt-dlp handles YouTube's anti-bot PO tokens internally during extract_info.
# The signed CDN subtitle URLs in info['automatic_captions'] bypass the issue.

def _parse_vtt(vtt_content: str):
    """Parse WebVTT into (start_seconds, text) tuples."""
    segments = []
    blocks = re.split(r'\n\n+', vtt_content)
    for block in blocks:
        lines = block.strip().split('\n')
        timestamp_line = None
        text_lines = []
        for i, line in enumerate(lines):
            if '-->' in line:
                timestamp_line = line
                text_lines = lines[i + 1:]
                break
        if not timestamp_line or not text_lines:
            continue
        match = re.match(r'(?:(\d+):)?(\d+):(\d+)[.,](\d+)', timestamp_line)
        if not match:
            continue
        h = int(match.group(1)) if match.group(1) else 0
        m, s, ms = int(match.group(2)), int(match.group(3)), int(match.group(4))
        start_s = h * 3600 + m * 60 + s + ms / 1000
        text = ' '.join(line.strip() for line in text_lines if line.strip())
        text = re.sub(r'<[^>]+>', '', text)  # strip VTT inline tags
        text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').strip()
        if text:
            segments.append((start_s, text))
    return segments


def _parse_json3(json_content: str):
    """Parse YouTube json3 caption format into (start_seconds, text) tuples."""
    segments = []
    try:
        data = json.loads(json_content)
    except json.JSONDecodeError:
        return segments
    for event in data.get('events', []):
        start_s = event.get('tStartMs', 0) / 1000
        text = ''.join(seg.get('utf8', '') for seg in event.get('segs', [])).strip()
        if text and text != '\n':
            segments.append((start_s, text))
    return segments


def _fetch_youtube_transcript(info: dict) -> Tuple[str, str]:
    """
    Fetch YouTube transcript from yt-dlp's signed CDN subtitle URLs.
    Priority: manual English → auto English → any language.
    Format preference: json3 > vtt > srv1.
    Returns (full_text, hook_text).
    """
    subtitles = info.get('subtitles', {})
    auto_captions = info.get('automatic_captions', {})
    lang_priority = ['en', 'en-US', 'en-GB', 'en-orig']
    preferred_exts = ('json3', 'vtt', 'srv1', 'srv2', 'srv3')

    def _pick_track(track_dict, langs=None):
        search_langs = langs if langs else list(track_dict.keys())
        for lang in search_langs:
            if lang not in track_dict:
                continue
            for ext in preferred_exts:
                for t in track_dict[lang]:
                    if t.get('ext') == ext:
                        return t['url'], ext
        return None, None

    url, ext = _pick_track(subtitles, lang_priority)
    if not url:
        url, ext = _pick_track(auto_captions, lang_priority)
    if not url:
        url, ext = _pick_track(subtitles)
    if not url:
        url, ext = _pick_track(auto_captions)
    if not url:
        raise Exception("No subtitle tracks in yt-dlp info dict.")

    resp = requests.get(url, timeout=15)
    resp.raise_for_status()

    segments = _parse_json3(resp.text) if ext == 'json3' else _parse_vtt(resp.text)
    if not segments:
        raise Exception(f"Subtitle file ({ext}) had no parseable segments.")

    full_text = ' '.join(t for _, t in segments)
    hook_text = ' '.join(t for s, t in segments if s <= 5.0) or "No hook available."
    return full_text, hook_text


# ── Main ingestion function ────────────────────────────────────────────────────

def process_video(url: str, tenant_id: int, video_label: str = "A") -> dict:
    """
    Universal ingestion: handles YouTube and Instagram.
    Fetches metadata, transcript, computes engagement rate,
    chunks into ChromaDB, writes to SQLite VideoMetadata.

    video_label: "A" or "B" — used to tag ChromaDB chunks and SQLite rows
                 so the agent can cite "Video A" or "Video B" in responses.
    """
    try:
        platform = detect_platform(url)
    except ValueError as e:
        return {"error": str(e)}

    # ── 1. Fetch metadata via yt-dlp ──────────────────────────────────────────
    ydl_opts = {"quiet": True, "no_warnings": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
        except Exception as e:
            return {"error": f"Failed to fetch metadata: {str(e)}"}

    views    = info.get("view_count", 0) or 0
    likes    = info.get("like_count", 0) or 0
    comments = info.get("comment_count", 0) or 0
    creator  = info.get("uploader", "Unknown")
    subs     = info.get("channel_follower_count", 0) or 0
    title    = info.get("title", "Unknown Video")
    tags     = info.get("tags", []) or []
    hashtags = json.dumps([f"#{t}" for t in tags[:15]])  # store top 15 as JSON
    upload_date = info.get("upload_date", "") or ""       # YYYYMMDD string
    duration    = info.get("duration", 0) or 0             # integer seconds

    # ── 2. Engagement rate ────────────────────────────────────────────────────
    engagement_rate = round(((likes + comments) / views * 100) if views > 0 else 0.0, 2)

    # ── 3. Transcript ─────────────────────────────────────────────────────────
    try:
        if platform == "youtube":
            transcript_text, hook_text = _fetch_youtube_transcript(info)
        else:
            transcript_text, hook_text = _fetch_instagram_transcript(url)
    except Exception as e:
        print(f"[RAG] Transcript unavailable ({platform}): {e}")
        transcript_text = "No transcript available for this video."
        hook_text       = "No hook available."

    # ── 4. Build ChromaDB document ────────────────────────────────────────────
    full_document = (
        f"VIDEO LABEL: {video_label}\n"
        f"VIDEO TITLE: {title}\n"
        f"PLATFORM: {platform}\n"
        f"VIDEO URL: {url}\n"
        f"CREATOR NAME: {creator}\n"
        f"CHANNEL SUBSCRIBERS: {subs:,}\n"
        f"TOTAL VIEWS: {views:,}\n"
        f"TOTAL LIKES: {likes:,}\n"
        f"TOTAL COMMENTS: {comments:,}\n"
        f"ENGAGEMENT RATE: {engagement_rate}%\n"
        f"UPLOAD DATE: {upload_date}\n"
        f"DURATION: {duration} seconds\n"
        f"HASHTAGS: {hashtags}\n"
        f"VIDEO HOOK (FIRST 5 SECONDS): {hook_text}\n\n"
        f"FULL TRANSCRIPT:\n{transcript_text}"
    )

    # Every chunk tagged with video_label + tenant_id for filtered retrieval
    doc_metadata = {
        "title":           title,
        "url":             url,
        "creator":         creator,
        "views":           views,
        "likes":           likes,
        "comments":        comments,
        "subs":            subs,
        "engagement_rate": engagement_rate,
        "platform":        platform,
        "video_label":     video_label,
        "tenant_id":       tenant_id,
    }

    # ── 5. Chunk + embed into ChromaDB ────────────────────────────────────────
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = text_splitter.create_documents([full_document], metadatas=[doc_metadata])
    vector_store.add_documents(chunks)

    # ── 6. Persist to SQLite ──────────────────────────────────────────────────
    with Session(engine) as session:
        video_record = VideoMetadata(
            url=url,
            title=title,
            creator=creator,
            views=views,
            likes=likes,
            comments=comments,
            subs=subs,
            engagement_rate=engagement_rate,
            hook_text=hook_text,
            hashtags=hashtags,
            upload_date=upload_date,
            duration=duration,
            platform=platform,
            video_label=video_label,
            tenant_id=tenant_id,
        )
        session.add(video_record)
        session.commit()

    return doc_metadata


# ── Backward-compat alias used in main.py ─────────────────────────────────────
def process_youtube_video(url: str, tenant_id: int) -> dict:
    """Legacy alias — process_video now handles both platforms."""
    return process_video(url, tenant_id, video_label="A")


def _detect_label_in_query(query: str) -> Optional[str]:
    """
    If the user says 'Video A' or 'Video B' explicitly, return that label.
    Otherwise return None and we search across all videos.

    Why this matters: pure semantic similarity doesn't know "Video B" is a label
    rather than a topic. Without this filter, asking "who's the creator of Video B?"
    could surface chunks from Video A whose creator name is semantically closer
    to the query. Filtering by metadata is deterministic.
    """
    q = query.lower()
    if re.search(r'\bvideo\s*a\b', q):
        return "A"
    if re.search(r'\bvideo\s*b\b', q):
        return "B"
    return None


def retrieve_context(query: str, tenant_id: int) -> list:
    """
    Returns list of (chunk_text, video_label) tuples.
    Uses max_marginal_relevance_search to diversify across videos.
    Returns list instead of string so agent.py can build citations.

    If the query explicitly mentions Video A or Video B, the search is scoped
    to that label via a Chroma metadata filter.
    """
    label_match = _detect_label_in_query(query)

    if label_match:
        chroma_filter = {
            "$and": [
                {"tenant_id":   {"$eq": tenant_id}},
                {"video_label": {"$eq": label_match}},
            ]
        }
    else:
        chroma_filter = {"tenant_id": tenant_id}

    docs = vector_store.max_marginal_relevance_search(
        query,
        k=4,
        fetch_k=20,
        filter=chroma_filter,
    )
    return [(doc.page_content, doc.metadata.get("video_label", "?")) for doc in docs]
