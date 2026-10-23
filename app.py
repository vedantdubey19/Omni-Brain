import os
import re
import time
import uuid
import streamlit as st
import requests

def escape_dollars(text: str) -> str:
    r"""
    Escapes unescaped dollar signs ($ -> \$) to prevent Streamlit from
    interpreting monetary figures (e.g., $199.9M ... $12M) as KaTeX LaTeX math.
    Skips dollar signs that are already escaped.
    """
    if not text or not isinstance(text, str):
        return text
    return re.sub(r'(?<!\\)\$', r'\$', text)


# ==========================================
# CONFIG & BACKEND CONNECTIVITY
# ==========================================

default_backend_url = os.getenv("BACKEND_URL", "https://omnibrain-backend-fw8h.onrender.com")


# ==========================================
# PAGE CONFIG
# ==========================================

st.set_page_config(
    page_title="OmniBrain • Multi-Agent RAG",
    page_icon="🧠",
    layout="wide"
)


# ==========================================
# SESSION STATE & HYDRATION (Fix 7)
# ==========================================

if "backend_url" not in st.session_state:
    st.session_state.backend_url = default_backend_url.rstrip("/")

BACKEND_URL = st.session_state.backend_url

# Synchronize session_id with browser query parameters across page reloads
query_params = st.query_params
url_session_id = query_params.get("session_id")

if "session_id" not in st.session_state:
    if url_session_id:
        st.session_state.session_id = url_session_id
    else:
        new_sid = str(uuid.uuid4())
        st.session_state.session_id = new_sid
        st.query_params["session_id"] = new_sid
else:
    if st.query_params.get("session_id") != st.session_state.session_id:
        st.query_params["session_id"] = st.session_state.session_id

if "uploaded_filename" not in st.session_state:
    st.session_state.uploaded_filename = None

if "uploaded_filetype" not in st.session_state:
    st.session_state.uploaded_filetype = None

if "pending_query" not in st.session_state:
    st.session_state.pending_query = None

# Hydrate chat_history from backend if empty in session state
if "chat_history" not in st.session_state or not st.session_state.chat_history:
    st.session_state.chat_history = []
    try:
        hist_resp = requests.get(
            f"{BACKEND_URL}/api/v1/chat/history/{st.session_state.session_id}",
            timeout=3.0
        )
        if hist_resp.status_code == 200:
            hist_data = hist_resp.json()
            messages = hist_data.get("messages", [])
            if messages:
                st.session_state.chat_history = messages
    except Exception:
        pass


# ==========================================
# HEADER
# ==========================================

st.title("🧠 OmniBrain")
st.caption("Multi-Agent Document Intelligence • LangGraph Supervisor Orchestration • Multi-Modal RAG")


# ==========================================
# SIDEBAR
# ==========================================

with st.sidebar:
    st.header("⚙️ System Connectivity")

    backend_input = st.text_input(
        "FastAPI Gateway URL",
        value=st.session_state.backend_url,
        help="Backend API address (e.g., https://omnibrain-backend-fw8h.onrender.com or http://127.0.0.1:8000)"
    )
    if backend_input and backend_input.rstrip("/") != st.session_state.backend_url:
        st.session_state.backend_url = backend_input.rstrip("/")
        st.rerun()

    BACKEND_URL = st.session_state.backend_url

    # Live Health Check
    try:
        health_resp = requests.get(f"{BACKEND_URL}/health", timeout=3.0)
        if health_resp.status_code == 200:
            st.success("🟢 Connected to Backend", icon="✅")
        else:
            st.warning(f"🟡 Backend returned HTTP {health_resp.status_code}")
    except Exception:
        st.error(f"🔴 Backend unreachable at `{BACKEND_URL}`")

    st.divider()

    st.header("📄 Active Artifact")
    if st.session_state.uploaded_filename:
        st.success(f"✅ Active: **{st.session_state.uploaded_filename}**")
        if st.session_state.uploaded_filetype:
            st.caption(f"Type: `{st.session_state.uploaded_filetype.upper()}`")
    else:
        st.info("Upload a PDF document, CSV dataset, or visual chart to begin.")

    st.divider()

    st.caption(f"**Session ID:** `{st.session_state.session_id[:8]}...`")

    if st.button("🗑️ Clear Chat History", use_container_width=True):
        # Clear backend chat history for this session as well
        try:
            requests.delete(
                f"{BACKEND_URL}/api/v1/chat/history/{st.session_state.session_id}",
                timeout=3.0
            )
        except Exception:
            pass
        new_sid = str(uuid.uuid4())
        st.session_state.session_id = new_sid
        st.query_params["session_id"] = new_sid
        st.session_state.chat_history = []
        st.rerun()


# ==========================================
# MULTI-FILE UPLOAD WIDGET (PDF, CSV, IMAGES)
# ==========================================

st.subheader("📁 Upload Document, Dataset, or Visual Chart")

uploaded_file = st.file_uploader(
    "Choose a file (PDF Document, CSV Financial Dataset, or Chart Image)",
    type=["pdf", "csv", "png", "jpg", "jpeg", "webp"]
)

if uploaded_file is not None:
    file_ext = os.path.splitext(uploaded_file.name)[1].lower()

    # 1. PDF Document Handling
    if file_ext == ".pdf":
        st.caption(f"📄 **PDF Document Selected:** `{uploaded_file.name}` ({len(uploaded_file.getvalue()) / 1024:.1f} KB)")
    if st.button("Upload & Index Document", type="primary"):
        with st.spinner("📤 Uploading document to OmniBrain API..."):
            try:
                files = {
                    "file": (
                        uploaded_file.name,
                        uploaded_file.getvalue(),
                        "application/pdf"
                    )
                }

                response = requests.post(
                    f"{BACKEND_URL}/api/v1/upload",
                    files=files,
                    timeout=120
                )

                if response.status_code in [200, 201]:
                    data = response.json()
                    job_id = data.get("job_id")
                    st.session_state.uploaded_filename = uploaded_file.name
                    st.info(f"📤 Uploaded successfully. Job ID: `{job_id}`.")

                    # Async Polling loop
                    progress_bar = st.progress(10, text="Job queued for processing...")
                    status_placeholder = st.empty()
                    max_poll_seconds = 60
                    poll_interval = 1.5
                    start_time = time.time()
                    job_completed = False

                    while time.time() - start_time < max_poll_seconds:
                        time.sleep(poll_interval)
                        elapsed = int(time.time() - start_time)
                        try:
                            status_resp = requests.get(
                                f"{BACKEND_URL}/api/v1/ingest/status/{job_id}",
                                timeout=5.0
                            )
                            if status_resp.status_code == 200:
                                status_info = status_resp.json()
                                job_status = status_info.get("status", "QUEUED")
                                msg = status_info.get("message", "")

                                if job_status == "QUEUED":
                                    progress_bar.progress(20, text=f"⏳ {msg} ({elapsed}s)")
                                elif job_status == "PROCESSING":
                                    progress_bar.progress(60, text=f"⚙️ {msg} ({elapsed}s)")
                                elif job_status == "COMPLETED":
                                    progress_bar.progress(100, text="✅ Document successfully ingested and indexed into vector DB!")
                                    status_placeholder.success(f"🎉 **{uploaded_file.name}** is fully processed and ready for querying!")
                                    job_completed = True
                                    break
                                elif job_status == "FAILED":
                                    err_detail = status_info.get("error_detail") or msg
                                    progress_bar.progress(100, text="❌ Ingestion failed")
                                    status_placeholder.error(f"❌ Ingestion failed: {err_detail}")
                                    job_completed = True
                                    break
                        except Exception as poll_err:
                            status_placeholder.warning(f"Polling connection warning: {poll_err}")

                    if not job_completed:
                        progress_bar.progress(90, text="⚠️ Processing taking longer than expected...")
                        status_placeholder.warning(
                            f"Document processing continues in the background. Job ID: `{job_id}`. "
                            "You can proceed with queries once complete."
                        )
                else:
                    st.error(f"❌ Upload failed with status code {response.status_code}: {response.text}")

            except requests.exceptions.ConnectionError:
                st.error("❌ Cannot connect to FastAPI backend at " + BACKEND_URL)
            except Exception as e:
                st.error(f"❌ Error during upload: {e}")

    # 2. CSV Financial Dataset Handling
    elif file_ext == ".csv":
        st.caption(f"📊 **CSV Financial Dataset Selected:** `{uploaded_file.name}` ({len(uploaded_file.getvalue()) / 1024:.1f} KB)")
        if st.button("📊 Upload & Ingest CSV into SQL Database", type="primary"):
            with st.spinner("📥 Loading structured historical data into SQLite database..."):
                try:
                    files = {
                        "file": (
                            uploaded_file.name,
                            uploaded_file.getvalue(),
                            "text/csv"
                        )
                    }
                    response = requests.post(
                        f"{BACKEND_URL}/api/v1/sql/load-csv",
                        files=files,
                        timeout=30
                    )
                    if response.status_code == 200:
                        csv_data = response.json()
                        rows_cnt = csv_data.get("rows_inserted", 0)
                        table_name = csv_data.get("table", "company_financials")
                        cols = csv_data.get("columns", [])
                        st.session_state.uploaded_filename = uploaded_file.name
                        st.session_state.uploaded_filetype = "csv"
                        st.success(
                            f"🎉 **{uploaded_file.name}** loaded successfully into table `{table_name}`! "
                            f"({rows_cnt} rows, columns: {', '.join(cols[:5])}...)"
                        )
                    else:
                        st.error(f"❌ CSV loading failed with status code {response.status_code}: {response.text}")
                except requests.exceptions.ConnectionError:
                    st.error(f"❌ Cannot connect to FastAPI backend at {BACKEND_URL}")
                except Exception as e:
                    st.error(f"❌ Error during CSV upload: {e}")

    # 3. Image Handling (Charts, Figures, Diagrams)
    elif file_ext in [".png", ".jpg", ".jpeg", ".webp"]:
        st.caption(f"🖼️ **Visual Artifact Selected:** `{uploaded_file.name}`")
        st.image(uploaded_file, caption=f"Preview: {uploaded_file.name}", width=450)
        if st.button("👁️ Upload & Register Image for Vision Agent", type="primary"):
            with st.spinner("📤 Registering visual artifact for VisionAgent multimodal analysis..."):
                try:
                    mime = "image/png" if file_ext == ".png" else "image/jpeg"
                    files = {
                        "file": (
                            uploaded_file.name,
                            uploaded_file.getvalue(),
                            mime
                        )
                    }
                    response = requests.post(
                        f"{BACKEND_URL}/api/v1/vision/upload-image",
                        files=files,
                        timeout=30
                    )
                    if response.status_code == 200:
                        st.session_state.uploaded_filename = uploaded_file.name
                        st.session_state.uploaded_filetype = "image"
                        st.success(f"🎉 **{uploaded_file.name}** uploaded and registered! Ask questions about this chart below.")
                    else:
                        st.error(f"❌ Image upload failed with status code {response.status_code}: {response.text}")
                except requests.exceptions.ConnectionError:
                    st.error(f"❌ Cannot connect to FastAPI backend at {BACKEND_URL}")
                except Exception as e:
                    st.error(f"❌ Error during image upload: {e}")


# ==========================================
# CURRENT DOCUMENT STATUS BANNER & QUICK DEMO PROMPTS
# ==========================================

if st.session_state.uploaded_filename:
    st.info(f"📌 Context Filter: **{st.session_state.uploaded_filename}** ({st.session_state.get('uploaded_filetype', 'file').upper()})")

# Interactive Quick Prompts for Demonstration
st.caption("💡 **Quick Demo Prompts (Click to Run):**")
prompt_cols = st.columns(3)

with prompt_cols[0]:
    if st.button("📄 Total FY2025 Revenue", use_container_width=True):
        st.session_state.pending_query = "What was Axelero Demo Corp's total revenue in fiscal year 2025?"
        st.rerun()

with prompt_cols[1]:
    if st.button("📊 Compare Q1 2025 vs Q1 2021", use_container_width=True):
        st.session_state.pending_query = "Compare Q1 2025 revenue to Q1 2021"
        st.rerun()

with prompt_cols[2]:
    if st.button("👁️ Highest Quarterly Revenue Chart", use_container_width=True):
        st.session_state.pending_query = "What was the highest quarterly revenue shown in the chart?"
        st.rerun()

st.divider()


# ==========================================
# CHAT INTERFACE
# ==========================================

st.subheader("💬 Chat with OmniBrain Multi-Agent Assistant")


# ------------------------------------------
# Render Past Messages
# ------------------------------------------

for message in st.session_state.chat_history:
    with st.chat_message(message["role"]):
        if message["role"] == "assistant":
            # Display past agent steps
            if message.get("execution_steps"):
                routed = message.get("routed_agent", "Agent")
                with st.expander(f"🤖 Handled by {routed} (View Decision Trace)", expanded=False):
                    for step in message["execution_steps"]:
                        agent_name = step.get("agent_name", "")
                        details = step.get("details") or {}
                        if agent_name == "SupervisorAgent":
                            route = details.get("route_chosen", routed)
                            reason = details.get("reasoning", "")
                            st.markdown(escape_dollars(f"- 🧭 **SupervisorAgent**: Routed to `{route}` *({reason})*"))
                        elif agent_name == "SearchAgent":
                            count = details.get("chunks_count", len(message.get("sources", [])))
                            st.markdown(escape_dollars(f"- 🔍 **SearchAgent**: Retrieved `{count}` chunk(s) via hybrid vector search"))
                        elif agent_name == "SQLAgent":
                            executed_sql = details.get("executed_sql") or message.get("executed_sql", "")
                            rows_count = details.get("row_count", 0)
                            sql_text = f" `{executed_sql}`" if executed_sql else ""
                            st.markdown(escape_dollars(f"- 📊 **SQLAgent**: Executed SQLite query{sql_text} ({rows_count} record(s) returned)"))
                        elif agent_name == "VisionAgent":
                            img_path = details.get("image_path")
                            msg = f"Analyzed visual artifact `{os.path.basename(img_path)}`" if img_path else details.get("message", "Visual multimodal analysis executed.")
                            st.markdown(escape_dollars(f"- 👁️ **VisionAgent**: {msg}"))
                        else:
                            st.markdown(escape_dollars(f"- ⚙️ **{agent_name}**: `{step.get('action_taken')}`"))

                    if message.get("retry_count", 0) > 0:
                        st.markdown(escape_dollars(f"- 🔄 **Self-RAG Optimization**: Refined query through `{message['retry_count']}` retry attempt(s)"))

            # Executed SQL Query viewer if applicable
            if message.get("executed_sql"):
                with st.expander("📊 Executed SQL Query & Data", expanded=False):
                    st.code(message["executed_sql"], language="sql")
                    if message.get("sql_results"):
                        st.dataframe(message["sql_results"], use_container_width=True)

            # Main text answer
            st.markdown(escape_dollars(message["content"]))

            # Sources accordion
            if message.get("sources"):
                with st.expander(f"📚 Sources & Citations ({len(message['sources'])} passages)", expanded=False):
                    for idx, source in enumerate(message["sources"], start=1):
                        fn = source.get("source") or source.get("filename", "Unknown Document")
                        page_num = source.get("page", 1)
                        score = source.get("score")
                        score_str = f" • Score: `{score:.4f}`" if score is not None else ""
                        content = source.get("content") or source.get("text", "")
                        st.markdown(escape_dollars(f"**{idx}. 📄 {fn}** (Page {page_num}{score_str})"))
                        st.text(content)
        else:
            st.markdown(escape_dollars(message["content"]))


# ------------------------------------------
# Chat Input & Real-Time Agent Execution
# ------------------------------------------

question = st.chat_input("Ask a question about your uploaded document or request chart analysis...")

active_query = question
if not active_query and st.session_state.get("pending_query"):
    active_query = st.session_state.pending_query
    st.session_state.pending_query = None

if active_query:
    # 1. Record and display user message
    st.session_state.chat_history.append({
        "role": "user",
        "content": active_query
    })

    with st.chat_message("user"):
        st.markdown(escape_dollars(active_query))

    # 2. Assistant execution via LangGraph Supervisor
    with st.chat_message("assistant"):
        with st.spinner("🧠 Supervisor evaluating query intent and orchestrating specialized agents..."):
            try:
                payload = {
                    "question": active_query,
                    "session_id": st.session_state.session_id,
                    "document_id": st.session_state.uploaded_filename
                }

                response = requests.post(
                    f"{BACKEND_URL}/api/v1/agent/query",
                    json=payload,
                    timeout=90
                )

                if response.status_code == 200:
                    data = response.json()

                    routed_agent = data.get("routed_agent", "SearchAgent")
                    final_answer = data.get("final_answer", "")
                    execution_steps = data.get("execution_steps", [])
                    referenced_sources = data.get("referenced_sources", [])
                    agent_status = data.get("status", "COMPLETED")

                    # Live visual execution steps container
                    with st.status(f"🤖 Handled by {routed_agent}", expanded=True) as status_box:
                        for step in execution_steps:
                            agent_name = step.get("agent_name", "")
                            action = step.get("action_taken", "")
                            details = step.get("details") or {}

                            if agent_name == "SupervisorAgent":
                                route = details.get("route_chosen", routed_agent)
                                reason = details.get("reasoning", "")
                                st.write(f"🧭 **Supervisor Decision**: Routed to `{route}`")
                                st.caption(escape_dollars(f"Reasoning: {reason}"))
                            elif agent_name == "SearchAgent":
                                count = details.get("chunks_count", len(referenced_sources))
                                st.write(f"🔍 **Search Agent**: Executed vector retrieval ({count} passages found)")
                            elif agent_name == "SQLAgent":
                                executed_sql = details.get("executed_sql") or data.get("executed_sql", "")
                                rows_count = details.get("row_count", 0)
                                st.write(f"📊 **SQL Agent**: Executed structured SQLite query ({rows_count} records)")
                                if executed_sql:
                                    st.code(executed_sql, language="sql")
                            elif agent_name == "VisionAgent":
                                img_path = details.get("image_path")
                                if img_path:
                                    st.write(f"👁️ **Vision Agent**: Multimodal visual analysis of `{os.path.basename(img_path)}`")
                                else:
                                    msg = details.get("message", "Visual multimodal reasoning completed.")
                                    st.write(escape_dollars(f"👁️ **Vision Agent**: {msg}"))
                            else:
                                st.write(f"⚙️ **{agent_name}**: {action}")

                        if data.get("retry_count", 0) > 0:
                            st.write(f"🔄 **Self-RAG Optimization**: Query re-evaluated through {data['retry_count']} refinement retry attempt(s)")

                        status_box.update(label=f"🤖 Handled by {routed_agent}", state="complete", expanded=False)

                    # Main Final Answer
                    st.markdown(escape_dollars(final_answer))

                    # Executed SQL Query accordion if applicable
                    if data.get("executed_sql"):
                        with st.expander("📊 Executed SQL Query & Data", expanded=False):
                            st.code(data["executed_sql"], language="sql")
                            if data.get("sql_results"):
                                st.dataframe(data["sql_results"], use_container_width=True)

                    # Grounded Sources Accordion
                    if referenced_sources:
                        with st.expander(f"📚 Sources & Citations ({len(referenced_sources)} passages)", expanded=False):
                            for idx, source in enumerate(referenced_sources, start=1):
                                fn = source.get("source", "Document")
                                page_num = source.get("page", 1)
                                score = source.get("score", 0.0)
                                content = source.get("content", "")
                                st.markdown(escape_dollars(f"**{idx}. 📄 {fn}** (Page {page_num} • Score: `{score:.4f}`)"))
                                st.text(content)

                    # Save to session history
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": final_answer,
                        "routed_agent": routed_agent,
                        "status": agent_status,
                        "execution_steps": execution_steps,
                        "sources": referenced_sources,
                        "executed_sql": data.get("executed_sql"),
                        "sql_results": data.get("sql_results"),
                        "retry_count": data.get("retry_count", 0),
                        "retry_history": data.get("retry_history", [])
                    })

                else:
                    st.error(f"❌ Backend error ({response.status_code}): {response.text}")

            except requests.exceptions.ConnectionError:
                st.error("❌ Cannot connect to FastAPI backend at " + BACKEND_URL)
            except requests.exceptions.Timeout:
                st.error("❌ Request timed out waiting for agent workflow.")
            except Exception as e:
                st.error(f"❌ Error during query processing: {e}")


# ==========================================
# FOOTER
# ==========================================

st.divider()
st.caption("OmniBrain • Multi-Agent RAG • LangGraph Supervisor • Qdrant Vector DB")