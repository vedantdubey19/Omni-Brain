import os
import re
import sys
from typing import Dict, Any, Literal, Optional
from langgraph.graph import StateGraph, END

# Support package and standalone paths
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from backend.app.services.retriever_service import RetrieverService
    from backend.app.services.llm_service import LLMSynthesisService
    from backend.app.services.sql_service import SQLQueryService
    from backend.app.services.vision_service import VisionAnalysisService
    from backend.app.services.agent_service import AgentGraphState
    from backend.app.services.tracing_service import tracing_service
except ImportError:
    from services.retriever_service import RetrieverService
    from services.llm_service import LLMSynthesisService
    try:
        from services.sql_service import SQLQueryService
    except ImportError:
        SQLQueryService = None
    try:
        from services.vision_service import VisionAnalysisService
    except ImportError:
        VisionAnalysisService = None
    from services.agent_service import AgentGraphState
    try:
        from services.tracing_service import tracing_service
    except ImportError:
        class _DummyTracing:
            def observe(self, *a, **k):
                def d(f):
                    return f
                return d
        tracing_service = _DummyTracing()

# Fallback service instances
retriever_service = RetrieverService()
llm_service = LLMSynthesisService()
sql_service = SQLQueryService() if SQLQueryService is not None else None
vision_service = VisionAnalysisService() if VisionAnalysisService is not None else None


def get_retriever_service() -> RetrieverService:
    """Retrieve shared retriever service instance from main app if running."""
    try:
        from backend.app.main import retriever_service as main_retriever
        return main_retriever
    except Exception:
        try:
            from main import retriever_service as main_retriever
            return main_retriever
        except Exception:
            return retriever_service


def get_llm_service() -> LLMSynthesisService:
    """Retrieve shared LLM service instance from main app if running."""
    try:
        from backend.app.main import llm_service as main_llm
        return main_llm
    except Exception:
        try:
            from main import llm_service as main_llm
            return main_llm
        except Exception:
            return llm_service


def get_sql_service() -> Optional[SQLQueryService]:
    """Retrieve shared SQL service instance or create new one."""
    global sql_service
    if sql_service is None:
        try:
            from backend.app.services.sql_service import SQLQueryService
            sql_service = SQLQueryService()
        except Exception:
            try:
                from services.sql_service import SQLQueryService
                sql_service = SQLQueryService()
            except Exception:
                sql_service = None
    return sql_service


def get_vision_service() -> Optional[VisionAnalysisService]:
    """Retrieve shared Vision service instance or create new one."""
    global vision_service
    if vision_service is None:
        try:
            from backend.app.services.vision_service import VisionAnalysisService
            vision_service = VisionAnalysisService()
        except Exception:
            try:
                from services.vision_service import VisionAnalysisService
                vision_service = VisionAnalysisService()
            except Exception:
                vision_service = None
    return vision_service


def classify_route(query: str, document_id: Optional[str] = None) -> str:
    """Determines target agent based on query characteristics and session document context."""
    query_lower = query.lower()

    # 1. Visual / Chart reasoning takes priority if visual artifact requested
    visual_keywords = ["image", "chart", "diagram", "figure", "plot", "graph", "picture", "visual", "layout"]
    if any(keyword.lower() in query_lower for keyword in visual_keywords):
        return "VisionAgent"

    if document_id and any(document_id.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp"]):
        return "VisionAgent"

    if document_id and document_id.lower().endswith(".csv"):
        return "SQLAgent"

    # 2. Text-to-SQL for structured, historical, or cross-period queries
    cross_period_patterns = [
        r"\bcompare\b",
        r"\btrend\b",
        r"\bover the years\b",
        r"\bover time\b",
        r"\bhistorical\b",
        r"\bacross (quarters|years|all years)\b",
        r"\b(highest|lowest|average)\b.{0,30}\brecorded\b",
        r"\bheadcount\b",
        r"\bemployee(s)?\b",
        r"\bshow (all|every) q\d\b",
        r"\bevery q[1-4]\b",
        r"\ball q[1-4]s?\b",
        r"\ball quarters\b",
        r"\bbetween 20\d\d\s+and\s+20\d\d\b",
        r"\bfrom 20\d\d\s+to\s+20\d\d\b",
        r"\bstructured data\b",
        r"\bdatabase\b",
        r"\b(total\s+)?revenue\s+in\s+q[1-4]\s+20\d\d\b",
        r"\b(revenue|profit|cogs|margin|headcount).{0,25}\b(q[1-4]|quarter\s*[1-4])\s*(?:of\s+)?20\d\d\b",
        r"\b(q[1-4]|quarter\s*[1-4])\s*(?:of\s+)?20\d\d.{0,25}\b(revenue|profit|cogs|margin|headcount)\b",
        r"\b(net\s+profit|profit|revenue|cogs|margin|headcount|expenses?).{0,25}\b20\d\d\b",
        r"\b20\d\d.{0,25}\b(net\s+profit|profit|revenue|cogs|margin|headcount|expenses?)\b"
    ]
    has_cross_period = any(re.search(pat, query_lower) for pat in cross_period_patterns)

    # Context-aware routing: If document is active in session
    if document_id:
        if not has_cross_period:
            return "SearchAgent"

        # Cheap guard: check if top-1 retrieval has confident hit (score >= 0.65)
        # without strong comparative cross-period wording
        strong_comparative = any(re.search(pat, query_lower) for pat in [
            r"\bcompare\b", r"\bacross (quarters|years|all)\b", r"\bover the years\b",
            r"\bheadcount\b", r"\brecorded\b", r"\bshow (all|every) q\b"
        ])
        if not strong_comparative:
            try:
                retriever = get_retriever_service()
                top1 = retriever.retrieve_relevant_chunks(query=query, top_k=1, document_id=document_id)
                if top1 and top1[0].get("score", 0.0) >= 0.65:
                    return "SearchAgent"
            except Exception:
                pass

        return "SQLAgent"

    # If no document is active
    if has_cross_period:
        return "SQLAgent"

    return "SearchAgent"


@tracing_service.observe(name="supervisor_node")
def supervisor_node(state: AgentGraphState) -> Dict[str, Any]:
    """
    Supervisor node that evaluates the query intent and assigns the appropriate target agent.
    """
    question = state.get("question", "")
    document_id = state.get("document_id")
    target_agent = classify_route(question, document_id=document_id)

    current_steps = state.get("execution_steps") or []
    intent_desc = (
        "visual/chart analysis" if target_agent == "VisionAgent"
        else "structured database/SQL query" if target_agent == "SQLAgent"
        else "semantic text retrieval"
    )
    step = {
        "step_number": len(current_steps) + 1,
        "agent_name": "SupervisorAgent",
        "action_taken": "ROUTING_DECISION",
        "details": {
            "route_chosen": target_agent,
            "reasoning": f"Query classified as {intent_desc}.",
            "target_document": state.get("document_id")
        }
    }

    print(f"[Supervisor] routed to: {target_agent}")

    return {
        "current_agent": target_agent,
        "execution_steps": [step]
    }


@tracing_service.observe(name="search_agent_node")
def search_agent_node(state: AgentGraphState) -> Dict[str, Any]:
    """
    Search agent node that executes real vector retrieval from Qdrant, bounded Self-RAG loop, and LLM synthesis.
    """
    question = state.get("question", "")
    document_id = state.get("document_id")

    active_retriever = get_retriever_service()
    active_llm = get_llm_service()

    # Initial retrieval pass
    chunks = active_retriever.retrieve_relevant_chunks(
        query=question,
        top_k=3,
        document_id=document_id
    )

    max_retries = int(os.getenv("SELF_RAG_MAX_RETRIES", "2"))
    avg_score = (
        sum(item.get("score", 0.0) for item in chunks) / len(chunks)
        if chunks else 0.0
    )
    is_low_confidence = (not chunks) or (avg_score < 0.65)

    retry_history = [{
        "attempt": 0,
        "query": question,
        "chunks_count": len(chunks),
        "avg_score": round(avg_score, 4),
        "passed_confidence": not is_low_confidence
    }]

    retry_count = 0
    current_q = question

    while is_low_confidence and retry_count < max_retries:
        retry_count += 1
        rewritten_q = active_llm.rewrite_query(
            vague_query=question,
            retrieved_chunks=chunks,
            attempt=retry_count
        )
        current_q = rewritten_q

        try:
            retry_chunks = active_retriever.retrieve_relevant_chunks(
                query=rewritten_q,
                top_k=3,
                document_id=document_id
            )
        except Exception:
            retry_chunks = []

        if retry_chunks:
            chunks = retry_chunks
            retry_avg_score = sum(item.get("score", 0.0) for item in retry_chunks) / len(retry_chunks)
            is_low_confidence = retry_avg_score < 0.65
            score_to_record = retry_avg_score
        else:
            is_low_confidence = True
            score_to_record = 0.0

        retry_history.append({
            "attempt": retry_count,
            "query": rewritten_q,
            "chunks_count": len(retry_chunks),
            "avg_score": round(score_to_record, 4),
            "passed_confidence": not is_low_confidence
        })

    # Real LLM synthesis call
    answer = active_llm.generate_answer(
        question=current_q,
        retrieved_chunks=chunks
    )

    current_steps = state.get("execution_steps") or []
    step = {
        "step_number": len(current_steps) + 1,
        "agent_name": "SearchAgent",
        "action_taken": "HYBRID_VECTOR_RETRIEVAL",
        "details": {
            "status": "RETRIEVED_CHUNKS",
            "chunks_count": len(chunks),
            "retry_count": retry_count,
            "low_confidence": is_low_confidence
        }
    }

    return {
        "current_agent": "SearchAgent",
        "retrieved_chunks": chunks,
        "final_answer": answer,
        "status": "COMPLETED",
        "retry_count": retry_count,
        "retry_history": retry_history,
        "execution_steps": [step]
    }


@tracing_service.observe(name="vision_agent_node")
def vision_agent_node(state: AgentGraphState) -> Dict[str, Any]:
    """
    Vision agent node that executes real multimodal visual reasoning via VisionAnalysisService.
    """
    question = state.get("question", "")
    document_id = state.get("document_id")
    active_vision = get_vision_service()

    if active_vision is None:
        answer = "Vision Agent service is currently unavailable."
        details = {"status": "UNAVAILABLE", "message": "Vision service not initialized."}
    else:
        image_path = active_vision.find_image_for_query(document_id, question)
        if image_path:
            result = active_vision.analyze_image(image_path, question)
            answer = result.get("summary", "")
            details = {
                "status": result.get("status", "COMPLETED"),
                "image_path": image_path,
                "is_fallback": result.get("is_fallback", False),
                "extracted_data": result.get("extracted_data")
            }
        else:
            answer = (
                "No visual artifacts (embedded charts, plots, or diagrams) were found "
                f"for document '{document_id or 'current session'}'. Please upload a PDF containing visual figures."
            )
            details = {
                "status": "NO_IMAGE_FOUND",
                "message": "No visual figures detected in target document context."
            }

    current_steps = state.get("execution_steps") or []
    step = {
        "step_number": len(current_steps) + 1,
        "agent_name": "VisionAgent",
        "action_taken": "VLM_MULTIMODAL_ANALYSIS",
        "details": details
    }

    return {
        "current_agent": "VisionAgent",
        "retrieved_chunks": [],
        "final_answer": answer,
        "status": "COMPLETED",
        "execution_steps": [step]
    }


@tracing_service.observe(name="sql_agent_node")
def sql_agent_node(state: AgentGraphState) -> Dict[str, Any]:
    """
    SQL agent node that executes Text-to-SQL generation and SQLite query execution.
    """
    question = state.get("question", "")
    active_sql = get_sql_service()
    if active_sql is None:
        answer = "SQL Agent service is unavailable."
        result = {"executed_sql": None, "rows": [], "row_count": 0, "status": "ERROR"}
    else:
        result = active_sql.query(question)
        answer = result.get("answer", "")

    current_steps = state.get("execution_steps") or []
    step = {
        "step_number": len(current_steps) + 1,
        "agent_name": "SQLAgent",
        "action_taken": "SQL_QUERY_EXECUTION",
        "details": {
            "status": result.get("status", "COMPLETED"),
            "executed_sql": result.get("executed_sql", ""),
            "row_count": result.get("row_count", 0),
            "success": result.get("success", True)
        }
    }

    return {
        "current_agent": "SQLAgent",
        "retrieved_chunks": [],
        "executed_sql": result.get("executed_sql"),
        "sql_results": result.get("rows"),
        "final_answer": answer,
        "status": result.get("status", "COMPLETED"),
        "execution_steps": [step]
    }


def router(state: AgentGraphState) -> Literal["search_agent", "vision_agent", "sql_agent"]:
    """Conditional routing edge function based on supervisor decision."""
    current_agent = state.get("current_agent")
    if current_agent == "VisionAgent":
        return "vision_agent"
    if current_agent == "SQLAgent":
        return "sql_agent"
    return "search_agent"


# Build LangGraph StateGraph
workflow = StateGraph(AgentGraphState)

workflow.add_node("supervisor", supervisor_node)
workflow.add_node("search_agent", search_agent_node)
workflow.add_node("vision_agent", vision_agent_node)
workflow.add_node("sql_agent", sql_agent_node)

workflow.set_entry_point("supervisor")

workflow.add_conditional_edges(
    "supervisor",
    router,
    {
        "search_agent": "search_agent",
        "vision_agent": "vision_agent",
        "sql_agent": "sql_agent"
    }
)

workflow.add_edge("search_agent", END)
workflow.add_edge("vision_agent", END)
workflow.add_edge("sql_agent", END)

workflow_graph = workflow.compile()
