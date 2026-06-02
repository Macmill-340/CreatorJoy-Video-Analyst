import os
from typing import TypedDict
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.output_parsers import StrOutputParser
from sqlmodel import Session, select
from agent.rag import retrieve_context, process_video  # noqa: F401  (re-export for convenience)
from backend.database import VideoMetadata, engine

load_dotenv()


class AgentState(TypedDict):
    user_input: str
    original_query: str
    history: str
    tenant_id: int
    intent: str
    context: str          # plain context string for critic
    cited_context: str    # context WITH [Video A, Chunk N] tags prepended
    final_answer: str


api_key = os.getenv("GEMINI_API_KEY")

# Synchronous LLM for planner (classification, no streaming needed)
base_llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash-lite", temperature=0.2, api_key=api_key)
llm = base_llm | StrOutputParser()

# Async streaming LLM for critic (final answer generation)
# Same model, streaming=True enables token-by-token async iteration
async_llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash-lite",
    temperature=0.2,
    api_key=api_key,
    streaming=True,
)


def planner_node(state: AgentState):
    query = state["original_query"]
    prompt = f"""You are a routing AI. Analyze the user's latest message: '{query}'

Output exactly one of these three words:

COMPARE - if they want to compare, contrast, or rank two videos against each other,
           or ask which video performed better, has a better hook, higher engagement, etc.

RAG - if they ask a factual or analytical question about one specific video
      (transcript content, a specific moment, one creator's stats, etc.)

CHAT - if they are making small talk, saying hello, or asking something unrelated to video analysis.

Output only the single word. No explanation."""

    intent_raw = llm.invoke(prompt).strip().upper()
    if "COMPARE" in intent_raw:
        intent = "COMPARE"
    elif "RAG" in intent_raw:
        intent = "RAG"
    else:
        intent = "CHAT"
    return {"intent": intent}


def executor_node(state: AgentState):
    intent    = state["intent"]
    query     = state["original_query"]
    tenant_id = state["tenant_id"]

    if intent == "RAG":
        # retrieve_context now returns list of (text, video_label) tuples
        results = retrieve_context(query, tenant_id)

        # Build cited context: prepend [Video A, Chunk N] to each chunk.
        # The LLM is instructed to include these tags in its answer.
        cited_parts = []
        for i, (chunk_text, video_label) in enumerate(results, 1):
            tag = f"[Video {video_label}, Chunk {i}]"
            cited_parts.append(f"{tag}\n{chunk_text}")

        cited_context = "\n\n".join(cited_parts)
        plain_context = "\n\n".join(chunk_text for chunk_text, _ in results)
        return {"context": plain_context, "cited_context": cited_context}


    elif intent == "COMPARE":
        with Session(engine) as session:
            v1 = session.exec(
                select(VideoMetadata)
                .where(VideoMetadata.tenant_id == tenant_id,
                       VideoMetadata.video_label == "A")
                .order_by(VideoMetadata.id.desc())
            ).first()
            v2 = session.exec(
                select(VideoMetadata)
                .where(VideoMetadata.tenant_id == tenant_id,
                       VideoMetadata.video_label == "B")
                .order_by(VideoMetadata.id.desc())
            ).first()

        if not v1 or not v2:
            ctx = ("Error: fewer than 2 videos analyzed. "

                   "Please ingest two URLs first.")

            return {"context": ctx, "cited_context": ctx}

        if len(videos) < 2:
            ctx = (
                "Error: fewer than 2 videos have been analyzed for this workspace. "
                "Please ingest two video URLs first."
            )
            return {"context": ctx, "cited_context": ctx}

        v2, v1 = videos[0], videos[1]  # newest first from DB, reverse for display

        ctx = (
            f"VIDEO A: '{v1.title}' by {v1.creator} [{v1.platform}]\n"
            f"  URL: {v1.url}\n"
            f"  Engagement Rate: {v1.engagement_rate}%\n"
            f"  Views: {v1.views:,}  |  Likes: {v1.likes:,}  |  Comments: {v1.comments:,}\n"
            f"  Subscribers: {v1.subs:,}  |  Duration: {v1.duration}s\n"
            f"  Upload Date: {v1.upload_date}  |  Hashtags: {v1.hashtags}\n"
            f"  Hook (First 5s): {v1.hook_text}\n\n"
            f"VIDEO B: '{v2.title}' by {v2.creator} [{v2.platform}]\n"
            f"  URL: {v2.url}\n"
            f"  Engagement Rate: {v2.engagement_rate}%\n"
            f"  Views: {v2.views:,}  |  Likes: {v2.likes:,}  |  Comments: {v2.comments:,}\n"
            f"  Subscribers: {v2.subs:,}  |  Duration: {v2.duration}s\n"
            f"  Upload Date: {v2.upload_date}  |  Hashtags: {v2.hashtags}\n"
            f"  Hook (First 5s): {v2.hook_text}\n"
        )
        return {"context": ctx, "cited_context": ctx}

    # CHAT — no tools
    return {"context": "No tools needed.", "cited_context": ""}


def build_critic_prompt(state: AgentState) -> str:
    """
    Extracted from critic_node so it can be used by both the synchronous
    run_agent() and the async streaming endpoint.
    """
    query         = state["original_query"]
    history       = state.get("history", "")
    intent        = state["intent"]
    cited_context = state.get("cited_context", state.get("context", ""))

    if intent == "RAG":
        return (
            f"You are an expert social media video analyst.\n"
            f"Answer based ONLY on the retrieved context below.\n"
            f"When citing information, include the source tag exactly as shown, "
            f"e.g. [Video A, Chunk 2], in your response so the user knows which video the info came from.\n\n"
            f"Recent conversation:\n{history}\n\n"
            f"Retrieved context:\n{cited_context}\n\n"
            f"User question: {query}"
        )
    elif intent == "COMPARE":
        # Gap fix: pass `history` through so multi-turn follow-ups
        # ("now elaborate on the hook", "what about hashtags?") stay coherent.
        return (
            f"You are an expert social media video analyst.\n"
            f"You have exact structured metrics for two videos. "
            f"Compare them clearly using the real numbers - do not estimate or invent figures.\n"
            f"Label them Video A and Video B throughout your response.\n"
            f"Highlight: Engagement Rate difference, Hook quality, Hashtag strategy, Duration, Subscriber gap.\n"
            f"End with: 'Suggestion for improvement:' - one concrete recommendation for the lower-performing video.\n\n"
            f"Recent conversation:\n{history}\n\n"
            f"Video data:\n{cited_context}\n\n"
            f"User question: {query}"
        )
    else:
        return (
            f"You are a friendly AI Video Analyst assistant.\n"
            f"Recent conversation:\n{history}\n\n"
            f"User: {query}\n\n"
            f"Reply warmly and helpfully."
        )


def critic_node(state: AgentState):
    prompt   = build_critic_prompt(state)
    response = llm.invoke(prompt)
    return {"final_answer": response}


# ── Graph (unchanged structure) ────────────────────────────────────────────────
workflow = StateGraph(AgentState)
workflow.add_node("planner", planner_node)
workflow.add_node("executor", executor_node)
workflow.add_node("critic", critic_node)
workflow.set_entry_point("planner")
workflow.add_edge("planner", "executor")
workflow.add_edge("executor", "critic")
workflow.add_edge("critic", END)
graph = workflow.compile()


def run_agent(user_input: str, history: str, tenant_id: int) -> str:
    """Synchronous path — used by /chat (kept for backward compat)."""
    result = graph.invoke({
        "user_input":    user_input,
        "original_query": user_input,
        "history":       history,
        "tenant_id":     tenant_id,
        "intent":        "",
        "context":       "",
        "cited_context": "",
        "final_answer":  "",
    })
    return str(result["final_answer"])


def run_planner_executor(user_input: str, history: str, tenant_id: int) -> AgentState:
    """
    Run ONLY planner + executor nodes synchronously.
    Used by the streaming endpoint so the slow LLM call (critic)
    can be streamed separately without buffering the whole answer.

    WHY separate: graph.invoke() buffers the entire response before returning.
    graph.astream_events() is the LangGraph way to stream per-token but adds
    complexity. Splitting planner+executor (fast, no streaming needed) from
    critic (slow, needs streaming) is simpler and equally correct.
    """
    state: AgentState = {
        "user_input":    user_input,
        "original_query": user_input,
        "history":       history,
        "tenant_id":     tenant_id,
        "intent":        "",
        "context":       "",
        "cited_context": "",
        "final_answer":  "",
    }
    state.update(planner_node(state))
    state.update(executor_node(state))
    return state
