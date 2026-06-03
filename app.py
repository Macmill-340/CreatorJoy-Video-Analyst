import os
import uuid
import time
import streamlit as st
import requests
import pandas as pd

BASE_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")

st.set_page_config(
    page_title="CreatorJoy Video Analyst",
    page_icon="📹",
    layout="wide",
)

# ── Session state initialisation ──────────────────────────────────────────────
if "token" not in st.session_state:
    st.session_state.token = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "vid1" not in st.session_state:
    st.session_state.vid1 = None
if "vid2" not in st.session_state:
    st.session_state.vid2 = None


def auth_headers():
    return {"Authorization": f"Bearer {st.session_state.token}"} if st.session_state.token else {}


st.title("📹 CreatorJoy AI Video Analyst")

tab_analyzer, tab_dashboard, tab_auth = st.tabs(
    ["💬 Video Analyzer", "📊 Admin Dashboard", "🔐 Login"]
)

# ── TAB 1: Video Analyzer ─────────────────────────────────────────────────────
with tab_analyzer:
    if not st.session_state.token:
        st.warning("⚠️ Please log in via the Login tab to access the Video Analyzer.")
    else:
        col_videos, col_chat = st.columns([4, 6])

        # LEFT COLUMN ─────────────────────────────────────────────────────────
        with col_videos:
            st.markdown("### 1. Ingest Videos")
            st.caption("Paste YouTube URLs to extract transcripts, hooks, and calculate engagement rate.")

            url1 = st.text_input("YouTube URL 1", placeholder="https://youtube.com/watch?v=...")
            url2 = st.text_input("YouTube URL 2", placeholder="https://youtube.com/watch?v=...")

            if st.button("Extract & Analyze"):
                if url1 and url2:
                    with st.spinner("Extracting metadata and transcripts (this takes a few seconds)..."):
                        try:
                            resp = requests.post(
                                f"{BASE_URL}/analyze_videos",
                                json={"url1": url1.strip(), "url2": url2.strip()},
                                headers=auth_headers(),
                            )
                            if resp.status_code == 200:
                                st.success("Videos successfully ingested into the Knowledge Base!")
                                st.session_state.vid1 = url1.strip()
                                st.session_state.vid2 = url2.strip()
                            else:
                                st.error(f"Failed to ingest videos: {resp.text}")
                        except Exception as e:
                            st.error(f"Backend connection error: {e}")
                else:
                    st.warning("Please provide two YouTube URLs to compare.")

            st.markdown("---")
            st.markdown("### 2. Video Preview")

            # ── RENDER FIX ───────────────────────────────────────────────────
            # The original code called st.rerun() after every chat reply.
            # That caused two full script runs per chat message: one natural
            # (from st.chat_input) and one explicit (st.rerun()). On the
            # second run the iframes were re-mounted mid-paint, producing the
            # double-washed-thumbnail flash. The fix is in the RIGHT COLUMN:
            # st.rerun() is removed there. With only one render pass per
            # submit the videos below never get torn down and rebuilt.
            # ─────────────────────────────────────────────────────────────────
            if st.session_state.vid1:
                st.video(st.session_state.vid1)
            if st.session_state.vid2:
                st.video(st.session_state.vid2)

        # RIGHT COLUMN ────────────────────────────────────────────────────────
        with col_chat:
            st.markdown("### 3. AI Analysis Chat")
            st.caption("Ask the agent to compare the hooks or engagement rates of the videos.")

            chat_container = st.container(height=600)

            with chat_container:
                for message in st.session_state.messages:
                    with st.chat_message(message["role"]):
                        st.markdown(message["content"])

            if prompt := st.chat_input("E.g., Compare the hooks in the first 5 seconds of both videos."):
                st.session_state.messages.append({"role": "user", "content": prompt})
                with chat_container:
                    with st.chat_message("user"):
                        st.markdown(prompt)

                history_list = st.session_state.messages[:-1]
                history_text = "\n".join(
                    [f"{m['role']}: {m['content']}" for m in history_list[-4:]]
                )

                with chat_container:
                    with st.chat_message("assistant"):
                        with st.spinner("Agent is analyzing..."):
                            try:
                                payload = {"message": prompt, "history": history_text}
                                response = requests.post(
                                    f"{BASE_URL}/chat",
                                    json=payload,
                                    headers=auth_headers(),
                                )
                                if response.status_code == 200:
                                    reply = response.json().get("reply", "No response.")
                                elif response.status_code == 401:
                                    reply = "🔒 Error: Unauthorized. Please log in again."
                                else:
                                    reply = f"Server Error: {response.text}"
                            except Exception as e:
                                reply = f"Failed to connect to backend: {e}"

                            st.markdown(reply)

                st.session_state.messages.append({"role": "assistant", "content": reply})
                # ── KEY FIX: st.rerun() removed ──────────────────────────────
                # st.chat_input already triggers one natural Streamlit rerun
                # when the user submits. The explicit st.rerun() here forced a
                # SECOND rerun immediately after the reply was rendered. That
                # second pass re-mounted the YouTube iframes mid-paint, causing
                # the washed double-thumbnail flash. Removing it means the
                # videos are only rendered once per submit. The messages are
                # already appended to st.session_state.messages above, so they
                # will appear correctly on the next natural rerun (next submit).
                # ─────────────────────────────────────────────────────────────

# ── TAB 2: Admin Dashboard ────────────────────────────────────────────────────
with tab_dashboard:
    if not st.session_state.token:
        st.warning("⚠️ Please log in to view the dashboard.")
    else:
        if st.button("🔄 Refresh Dashboard"):
            st.session_state["dash_videos"] = None
            st.session_state["dash_traces"] = None

        if "dash_videos" not in st.session_state:
            st.session_state["dash_videos"] = None
        if "dash_traces" not in st.session_state:
            st.session_state["dash_traces"] = None

        try:
            v_resp = requests.get(f"{BASE_URL}/videos", headers=auth_headers())
            if v_resp.status_code == 200:
                st.session_state["dash_videos"] = v_resp.json()
        except Exception as e:
            st.error(f"Could not load videos: {e}")

        try:
            t_resp = requests.get(f"{BASE_URL}/traces?limit=20", headers=auth_headers())
            if t_resp.status_code == 200:
                st.session_state["dash_traces"] = t_resp.json()
        except Exception as e:
            st.error(f"Could not load traces: {e}")

        st.markdown("### 📹 Ingested Video Database")
        st.caption("Metadata and engagement metrics extracted per analysis session.")

        videos = st.session_state.get("dash_videos")
        if videos:
            df_v = pd.DataFrame(videos)
            df_v = df_v.drop(columns=["id", "tenant_id", "thumbnail_url"], errors="ignore")
            st.dataframe(df_v, use_container_width=True)
        else:
            st.info("No videos analyzed yet.")

        st.markdown("---")

        st.markdown("### 🔍 Agent Traces & Cost Observability")
        st.caption("Latency, token usage, and estimated cost per chat query.")

        traces = st.session_state.get("dash_traces")
        if traces:
            df_t = pd.DataFrame(traces)
            df_t = df_t.drop(columns=["id", "tenant_id", "session_id"], errors="ignore")

            total_cost    = df_t["estimated_cost"].sum()
            avg_latency   = df_t["latency_ms"].mean()
            total_queries = len(df_t)
            total_tokens  = (df_t["input_tokens"] + df_t["output_tokens"]).sum()

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Queries",  total_queries)
            m2.metric("Avg Latency",    f"{avg_latency:,.0f} ms")
            m3.metric("Total Tokens",   f"{total_tokens:,}")
            m4.metric("Estimated Cost", f"${total_cost:.4f}")

            display_cols = [
                "user_input", "latency_ms", "input_tokens",
                "output_tokens", "estimated_cost",
                "faithfulness", "hallucination_rate", "retrieval_quality",
                "created_at",
            ]
            display_cols = [c for c in display_cols if c in df_t.columns]
            st.dataframe(df_t[display_cols], use_container_width=True)
        else:
            st.info("No agent traces yet — send a chat message first.")

# ── TAB 3: Login ──────────────────────────────────────────────────────────────
with tab_auth:
    if st.session_state.token:
        st.success("✅ You are logged in and authenticated.")
        if st.button("Logout"):
            st.session_state.token = None
            st.session_state.messages = []
            st.session_state.vid1 = None
            st.session_state.vid2 = None
            st.rerun()
    else:
        st.info("Default credentials: **admin** / **admin123**")

        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login")

        if submitted:
            try:
                response = requests.post(
                    f"{BASE_URL}/login",
                    data={"username": username, "password": password},
                )
                if response.status_code == 200:
                    st.session_state.token = response.json().get("access_token")
                    st.success("Login successful! Switch to the Video Analyzer tab.")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Invalid credentials.")
            except Exception as e:
                st.error(f"Connection failed: {e}")