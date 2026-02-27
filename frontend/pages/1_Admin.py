"""Admin Panel – Document ingestion and management.

Accessible only to admin users (enforced by API).
"""

from __future__ import annotations

import os

import httpx
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

API_BASE = os.getenv("API_BASE_URL", "http://backend:8000")

st.set_page_config(page_title="Admin – Document Manager", page_icon="🔧", layout="wide")


def _headers() -> dict:
    if st.session_state.get("token"):
        return {"Authorization": f"Bearer {st.session_state['token']}"}
    return {}


def _require_admin():
    if not st.session_state.get("token"):
        st.error("You must be logged in. Please return to the main page.")
        st.stop()
    if not st.session_state.get("is_admin"):
        st.error("Admin access required.")
        st.stop()


_require_admin()

st.title("🔧 Admin – Document Manager")
st.caption("Upload, list, and delete documents in the RAG knowledge base.")

st.divider()

# ── Upload ────────────────────────────────────────────────────────────────────
st.subheader("📤 Upload Document")
uploaded = st.file_uploader(
    "Supported formats: .md, .txt, .pdf, .docx",
    type=["md", "txt", "pdf", "docx"],
)

if uploaded and st.button("Ingest Document", type="primary"):
    with st.spinner("Ingesting…"):
        try:
            with httpx.Client(base_url=API_BASE, timeout=120) as client:
                resp = client.post(
                    "/api/ingest",
                    headers=_headers(),
                    files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type)},
                )
            resp.raise_for_status()
            data = resp.json()
            if data["deduplicated"]:
                st.warning(f"⚠️ Document already exists (deduplicated). Document ID: {data['document_id']}")
            else:
                st.success(
                    f"✅ Ingested **{data['filename']}** — "
                    f"{data['chunks_created']} chunks created (ID: {data['document_id']})"
                )
        except httpx.HTTPStatusError as e:
            st.error(f"API error {e.response.status_code}: {e.response.text}")
        except Exception as e:
            st.error(f"Error: {e}")

st.divider()

# ── Document list ─────────────────────────────────────────────────────────────
st.subheader("📚 Knowledge Base Documents")

if st.button("🔄 Refresh", key="refresh_docs"):
    st.rerun()

try:
    with httpx.Client(base_url=API_BASE, timeout=30) as client:
        resp = client.get("/api/ingest", headers=_headers())
    resp.raise_for_status()
    docs = resp.json()
except Exception as e:
    st.error(f"Failed to load documents: {e}")
    docs = []

if not docs:
    st.info("No documents ingested yet. Upload a document above to get started.")
else:
    for doc in docs:
        col1, col2, col3, col4 = st.columns([3, 1, 2, 1])
        with col1:
            st.write(f"📄 **{doc['filename']}**")
        with col2:
            st.write(f"{doc['chunk_count']} chunks")
        with col3:
            st.caption(doc["created_at"])
        with col4:
            if st.button("🗑️ Delete", key=f"del_{doc['id']}"):
                try:
                    with httpx.Client(base_url=API_BASE, timeout=30) as client:
                        r = client.delete(f"/api/ingest/{doc['id']}", headers=_headers())
                    r.raise_for_status()
                    st.success("Deleted.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Delete failed: {e}")

st.divider()

# ── Health check ──────────────────────────────────────────────────────────────
st.subheader("🩺 System Health")

if st.button("Check health"):
    try:
        with httpx.Client(base_url=API_BASE, timeout=10) as client:
            resp = client.get("/health")
        resp.raise_for_status()
        h = resp.json()
        st.json(h)
        if h.get("status") == "ok":
            st.success("All systems nominal.")
        else:
            st.warning("System degraded — check logs.")
    except Exception as e:
        st.error(f"Health check failed: {e}")
