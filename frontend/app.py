"""AI Career Assistant – Streamlit Chat UI.

Main page: authenticated chat with cited RAG answers.
"""

from __future__ import annotations

import os

import httpx
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

API_BASE = os.getenv("API_BASE_URL", "http://backend:8000")

st.set_page_config(
    page_title="AI Career Assistant",
    page_icon="💼",
    layout="centered",
    initial_sidebar_state="expanded",
)

# ── Session state defaults ────────────────────────────────────────────────────
for key, default in {
    "token": None,
    "username": None,
    "is_admin": False,
    "session_id": None,
    "messages": [],
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ── API helpers ───────────────────────────────────────────────────────────────

def api_post(path: str, json: dict | None = None, auth: bool = True) -> dict:
    headers = {}
    if auth and st.session_state.token:
        headers["Authorization"] = f"Bearer {st.session_state.token}"
    with httpx.Client(base_url=API_BASE, timeout=120) as client:
        resp = client.post(path, json=json, headers=headers)
    resp.raise_for_status()
    return resp.json()


def api_get(path: str, auth: bool = True) -> dict | list:
    headers = {}
    if auth and st.session_state.token:
        headers["Authorization"] = f"Bearer {st.session_state.token}"
    with httpx.Client(base_url=API_BASE, timeout=30) as client:
        resp = client.get(path, headers=headers)
    resp.raise_for_status()
    return resp.json()


# ── Auth sidebar ──────────────────────────────────────────────────────────────

def render_sidebar():
    with st.sidebar:
        st.title("💼 AI Career Assistant")
        st.caption("Powered by RAG + Local LLM")

        st.divider()

        if st.session_state.token is None:
            tab_login, tab_register = st.tabs(["Login", "Register"])

            with tab_login:
                email = st.text_input("Email", key="login_email")
                password = st.text_input("Password", type="password", key="login_pass")
                if st.button("Login", use_container_width=True):
                    try:
                        data = api_post("/api/users/login", json={"email": email, "password": password}, auth=False)
                        st.session_state.token = data["token"]
                        st.session_state.username = data["username"]
                        st.session_state.is_admin = data["is_admin"]
                        st.success(f"Welcome, {data['username']}!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Login failed: {e}")

            with tab_register:
                r_username = st.text_input("Username", key="reg_user")
                r_email = st.text_input("Email", key="reg_email")
                r_password = st.text_input("Password", type="password", key="reg_pass")
                if st.button("Register", use_container_width=True):
                    try:
                        data = api_post("/api/users", json={
                            "username": r_username, "email": r_email, "password": r_password
                        }, auth=False)
                        st.session_state.token = data["token"]
                        st.session_state.username = data["username"]
                        st.session_state.is_admin = data["is_admin"]
                        st.success("Account created!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Registration failed: {e}")
        else:
            st.success(f"👤 {st.session_state.username}")
            if st.session_state.is_admin:
                st.badge("Admin", color="blue")
            if st.button("🔄 New conversation"):
                st.session_state.session_id = None
                st.session_state.messages = []
                st.rerun()
            if st.button("Logout", use_container_width=True):
                for k in ("token", "username", "is_admin", "session_id", "messages"):
                    st.session_state[k] = None if k == "token" else ([] if k == "messages" else None)
                st.rerun()

        st.divider()
        st.caption("ℹ️ Answers are based on ingested profile documents.")
        st.caption(f"API: `{API_BASE}`")


# ── Main chat UI ──────────────────────────────────────────────────────────────

def render_chat():
    st.header("Ask me about the candidate")

    if st.session_state.token is None:
        st.info("👈 Please login from the sidebar to start chatting.")
        return

    # Render message history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("citations"):
                with st.expander(f"📚 {len(msg['citations'])} source(s)", expanded=False):
                    for c in msg["citations"]:
                        st.markdown(f"**[Source {c['index']}]** `{c['source_label']}`")
                        st.caption(f"> {c['excerpt']}")

    # Input
    if prompt := st.chat_input("e.g. What programming languages does the candidate know?"):
        # Show user message immediately
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Call API
        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                try:
                    payload: dict = {"question": prompt}
                    if st.session_state.session_id:
                        payload["session_id"] = st.session_state.session_id

                    data = api_post("/api/chat", json=payload)
                    st.session_state.session_id = data["session_id"]

                    answer = data["answer"]
                    citations = data.get("citations", [])

                    st.markdown(answer)
                    if citations:
                        with st.expander(f"📚 {len(citations)} source(s)", expanded=False):
                            for c in citations:
                                st.markdown(f"**[Source {c['index']}]** `{c['source_label']}`")
                                st.caption(f"> {c['excerpt']}")

                    if not data.get("has_evidence"):
                        st.warning("⚠️ No relevant evidence found in the knowledge base.")

                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": answer,
                        "citations": citations,
                    })
                except Exception as e:
                    error_msg = f"Error: {e}"
                    st.error(error_msg)
                    st.session_state.messages.append({"role": "assistant", "content": error_msg})


# ── Entry point ───────────────────────────────────────────────────────────────

render_sidebar()
render_chat()
