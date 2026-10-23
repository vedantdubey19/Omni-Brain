# OmniBrain

**Agentic Multi-Modal RAG Orchestrator for Complex Document Reasoning**

[![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph-1c3d5a)](https://github.com/langchain-ai/langgraph)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688)](https://fastapi.tiangolo.com/)
[![Streamlit](https://img.shields.io/badge/Frontend-Streamlit-ff4b4b)](https://streamlit.io/)
[![Qdrant](https://img.shields.io/badge/Vector%20DB-Qdrant-dc244c)](https://qdrant.tech/)
[![Observability](https://img.shields.io/badge/Observability-Langfuse-e05d44)](https://langfuse.com)
[![Guardrails](https://img.shields.io/badge/Guardrails-Custom%20Hybrid%20Engine-4c1)]()
[![Status](https://img.shields.io/badge/status-production--ready-brightgreen)]()

---

## Overview

Standard Retrieval-Augmented Generation (RAG) pipelines break down when documents mix unstructured text with **financial tables, embedded charts, images, and structured historical data**, or when a query requires **multi-step reasoning across heterogeneous data silos**.

**OmniBrain** is an enterprise agentic, multi-modal RAG orchestrator built around a **LangGraph supervisor architecture**. It analyzes user intent and dynamically routes incoming queries to the right specialist agent — semantic search, SQL, or vision — executes bounded self-correction loops (Self-RAG), and returns a fully cited, grounded response.

### Use Case

A quantitative analyst uploads a **corporate financial PDF**. OmniBrain:
1. Parses embedded text, tables, and charts with OCR fallback
2. Retrieves relevant semantic text chunks from a Qdrant vector database
3. Queries historical financial records via a safe Text-to-SQL agent
4. Analyzes embedded figures and visual trends using a Vision-Language Model (Gemini / GPT-4o)
5. Synthesizes outputs into a cited response — with every claim traceable back to its source page, table, or chart

---

## Application & Architecture Gallery

| **1. Streamlit Interactive Dashboard** | **2. FastAPI OpenAPI / Swagger Gateway** |
|:---:|:---:|
| ![Streamlit UI](docs/screenshots/01_streamlit_dashboard.png) | ![FastAPI Docs](docs/screenshots/02_fastapi_swagger_docs.png) |
| *Multi-Agent conversational interface with document ingestion and session routing* | *REST API gateway with LangGraph orchestration endpoints* |

| **3. Extracted Multimodal Visual Artifact** |
|:---:|
| ![Extracted Chart](docs/screenshots/03_extracted_multimodal_chart.png) |
| *Embedded quarterly revenue chart parsed by PyMuPDF and analyzed by the VisionAgent* |

---

## System Architecture

```
                         ┌───────────────────────────┐
                         │   User Query (Streamlit)   │
                         └─────────────┬───────────────┘
                                       │
                               ┌───────▼───────────┐
                               │  Enterprise       │
                               │  Input Guardrails │
                               └───────┬───────────┘
                                       │
                               ┌───────▼───────────┐
                               │  LangGraph        │
                               │  Supervisor Node  │
                               └───┬───┬───────┬───┘
                   ┌───────────────┘   │       └───────────────┐
                   │                   │                       │
          ┌────────▼─────────┐  ┌──────▼───────┐      ┌────────▼─────────┐
          │   Search Agent   │  │  SQL Agent   │      │  Vision Agent    │
          │ (Qdrant Vector)  │  │ (SQLite AST) │      │  (GPT-4o Vision) │
          └────────┬─────────┘  └──────┬───────┘      └────────┬─────────┘
                   │                   │                       │
                   └───────────┬───────┴───────────┬───────────┘
                               │                   │
                      ┌────────▼───────────────────▼────────┐
                      │      Self-RAG Correction Loop       │
                      │  (multi-step adaptive query rewrite) │
                      └────────────────┬────────────────────┘
                                       │
                          ┌────────────▼─────────────┐
                          │  Enterprise Output Rails │
                          │  (PII / Secret Redactor) │
                          │  + Tracing (Langfuse)    │
                          └────────────┬─────────────┘
                                       │
                            ┌──────────▼──────────┐
                            │  Cited Synthesized  │
                            │  Response (FastAPI) │
                            └─────────────────────┘
```

---

## Key Modules

| Module | Stack | Responsibility |
|---|---|---|
| **Agentic Orchestrator** | LangGraph StateGraph | Manages state, memory, and conditional routing across Search, SQL, and Vision agents |
| **Vector Retrieval** | Qdrant (Local / Cloud) + SentenceTransformers | Stores and retrieves dense text embeddings (`all-MiniLM-L6-v2`) with document-scoped filtering |
| **Vision Agent** | GPT-4o Vision API + Pillow | Multimodal image reasoning over charts and figures with graceful offline metadata fallback |
| **Text-to-SQL Agent** | SQLite3 + AST Validator | Safe read-only execution against structured financial data (FY2020–FY2025) |
| **Self-RAG Loop** | Adaptive TF-IDF / LLM Rewriter | Bounded multi-step correction loop (`max_retries=2`) triggered on low-confidence retrieval |
| **Guardrails** | Enterprise Custom Hybrid Engine | High-precision regex first-pass + optional secondary LLM intent check + output key redaction |
| **Observability** | Langfuse | Traces latency, token usage, retry loops, and agent steps with graceful mock fallback |
| **PDF Ingestion** | PyMuPDF + pdfplumber + Tesseract | Text extraction, table parsing, embedded image harvesting, and OCR fallback |

---

## Tech Stack

- **Orchestration:** LangGraph, LangChain
- **Backend:** FastAPI, Uvicorn, Pydantic v2
- **Frontend:** Streamlit (thought-process timeline, multimodal image rendering, interactive citations)
- **Vector Store:** Qdrant (Docker container and Qdrant Cloud managed)
- **Embeddings:** `sentence-transformers/all-MiniLM-L6-v2` (pre-cached, offline-safe)
- **Vision-Language Model:** OpenAI GPT-4o Vision (with offline Pillow inspection fallback)
- **Structured Database:** SQLite3 with AST-enforced read-only safety
- **Observability:** Langfuse (`@tracing_service.observe`)
- **Guardrails:** Custom Enterprise Guardrails Engine (Input injection blocklist + secondary LLM verifier + output secret redactor)
- **Deployment:** Docker, Docker Compose, Render (`render.yaml`), Fly.io (`fly.toml`)

---

## Project Status

- ✅ **Phase 0: Repo Hygiene & CI** — Merged upstream branches (`main` and `dev` in sync), verified clean CI pass.
- ✅ **Phase 1: Text-to-SQL Agent** — Structured SQLite analytical database, read-only SQL validation, LangGraph supervisor node, and Streamlit execution trace rendering.
- ✅ **Phase 2: Vision Agent** — GPT-4o multimodal image analysis, Pillow inspection fallback, automatic image linkage during PDF ingestion, and Streamlit image display.
- ✅ **Phase 3: Self-RAG Correction Loop** — Bounded multi-step retry loop (`max_retries=2`), adaptive cross-domain query rewriter, `retry_count` and `retry_history` tracking across API and UI.
- ✅ **Phase 4: Enterprise Guardrails** — High-precision regex first-pass filtering, secondary LLM adversarial intent check, and output credential/token redaction.
- ✅ **Phase 5: Cloud Deployment** — Production blueprints for Render (`render.yaml`) and Fly.io (`fly.toml`), Qdrant Cloud managed cluster integration, and comprehensive environment templates.
- ✅ **Phase 6: Documentation Truthfulness Pass** — Fully aligned documentation, updated API reference covering all 8 endpoints, and verified operational status.

---

## Repository Structure

```
OmniBrain/
├── backend/                  # Backend FastAPI Service
│   ├── app/
│   │   ├── agents/           # LangGraph Agent Orchestrators
│   │   │   └── supervisor.py # Intent router & multi-agent execution graph
│   │   ├── services/         # Modular production service layer
│   │   │   ├── agent_service.py     # State management & agent invocation
│   │   │   ├── citation_service.py  # Exact page snippets & visual boundaries
│   │   │   ├── guardrails_service.py# Injection detection & output redaction
│   │   │   ├── job_store.py         # Persistent SQLite job & session history
│   │   │   ├── llm_client.py        # OpenAI / Gemini API fallback resolution
│   │   │   ├── llm_service.py       # Synthesis & Self-RAG query rewriter
│   │   │   ├── retriever_service.py # Qdrant dense vector store singleton
│   │   │   ├── sql_service.py       # Safe read-only SQLite Text-to-SQL
│   │   │   ├── tracing_service.py   # Langfuse observability decorator
│   │   │   └── vision_service.py    # GPT-4o multimodal chart analysis
│   │   └── main.py           # FastAPI Gateway & REST routing endpoints
│   └── __init__.py
├── frontend/                 # Frontend Web Interface
│   ├── .streamlit/           # Custom blush/rose theme configuration
│   │   └── config.toml
│   ├── app.py                # Streamlit production dashboard application
│   ├── Dockerfile            # Container deployment for frontend
│   ├── requirements.txt      # Frontend Python dependencies
│   └── react_ui/             # Optional standalone React + Vite client
├── pdf_parser_module/        # PyMuPDF Document Extraction Pipeline
│   ├── app/
│   │   ├── core/             # Configuration & logging
│   │   ├── models/           # Pydantic schema contracts
│   │   ├── services/         # OCR, table extraction, and image parsing
│   │   └── utils/            # Bounding box & PDF helper utilities
│   ├── requirements.txt      # Parser dependencies
│   └── README.md
├── docs/                     # Technical documentation & architecture assets
│   ├── screenshots/          # Production UI & API gallery images
│   ├── api_reference.md      # Comprehensive endpoint documentation
│   └── setup.md              # Detailed local & cloud deployment guide
├── data/                     # Local file storage (runtime generated)
│   ├── raw/                  # Uploaded documents
│   └── .gitkeep
├── .env.example              # Environment variables template
├── .gitignore                # Production git ignore configuration
├── app.py                    # Root entrypoint redirecting to frontend/app.py
├── docker-compose.yml        # Multi-service local Docker orchestration
├── Dockerfile                # Production Backend Docker image
├── render.yaml               # Infrastructure-as-code for Render deployment
├── requirements.txt          # Production backend dependencies
└── Readme.md                 # Project overview and reference guide
```

---

## Getting Started

### 1. Clone & Configure Environment

```bash
git clone https://github.com/vedantdubey19/Omni-Brain.git
cd Omni-Brain
cp .env.example .env
```

### 2. Native Setup

```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start Backend API Gateway (FastAPI)
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload

# In another terminal: Start Frontend Dashboard (Streamlit)
source .venv/bin/activate
streamlit run frontend/app.py --server.port 8501
```

### 3. Containerized Setup (Docker Compose)

```bash
docker compose up --build
```

- **Backend Gateway & Swagger Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Frontend UI:** [http://localhost:8501](http://localhost:8501)
- **Qdrant Dashboard:** [http://localhost:6333/dashboard](http://localhost:6333/dashboard)

---

## Live Cloud Production

- **Backend API Gateway:** [https://omnibrain-backend-fw8h.onrender.com](https://omnibrain-backend-fw8h.onrender.com)
- **Frontend Web Application:** [https://omnibrain-frontend-6och.onrender.com](https://omnibrain-frontend-6och.onrender.com)
- **OpenAPI Interactive Documentation:** [https://omnibrain-backend-fw8h.onrender.com/docs](https://omnibrain-backend-fw8h.onrender.com/docs)

---

## License

MIT License — feel free to fork and build on this.
