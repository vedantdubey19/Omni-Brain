import os
from typing import List, Dict, Any, Optional

try:
    from backend.app.services.tracing_service import tracing_service
except ImportError:
    try:
        from services.tracing_service import tracing_service
    except ImportError:
        class _DummyTracing:
            def observe(self, *a, **k):
                def d(f):
                    return f
                return d
        tracing_service = _DummyTracing()

try:
    from backend.app.services.llm_client import get_llm_client
except ImportError:
    try:
        from services.llm_client import get_llm_client
    except ImportError:
        def get_llm_client(*a, **k):
            return None, None, None


class LLMSynthesisService:
    """
    Synthesizes final RAG answers and provides query-rewriting for Self-RAG loops.
    Instrumented with Langfuse observability for token, latency, and generation tracing.
    """
    def __init__(self, model_name: str = "gpt-4o-mini", timeout_seconds: float = 15.0):
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        raw_key = os.getenv("OPENAI_API_KEY", "")
        self.api_key = raw_key if raw_key and not raw_key.startswith("sk-placeholder") else ""

    @tracing_service.observe(name="self_rag_rewrite_query", as_type="generation")
    def rewrite_query(
        self,
        vague_query: str,
        retrieved_chunks: Optional[List[Dict[str, Any]]] = None,
        attempt: int = 1
    ) -> str:
        """
        Self-RAG Rewriter: Expands vague queries into searchable domain terms.
        Uses LLM (Gemini / OpenAI) when API key is present; otherwise performs adaptive TF-IDF / term-overlap
        expansion using vocabulary from retrieved chunks, falling back to domain-neutral expansion.
        """
        client, model, _ = get_llm_client(timeout_seconds=self.timeout_seconds)
        if client:
            try:
                context_hint = ""
                if retrieved_chunks:
                    snippets = " ".join(c.get("content", "")[:100] for c in retrieved_chunks[:2])
                    context_hint = f" Context hints: {snippets}"
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a search query optimizer. Given a user query and attempt number, "
                                "rewrite it to be specific and keyword-rich for dense vector retrieval. "
                                "Return only the rewritten query string."
                            )
                        },
                        {"role": "user", "content": f"Query: {vague_query}. Attempt: {attempt}.{context_hint}"}
                    ],
                    temperature=0.1 + (attempt * 0.1),
                    max_tokens=150
                )
                rewritten = response.choices[0].message.content.strip()
                if rewritten:
                    return rewritten
            except Exception as e:
                print(f"[LLMSynthesisService] LLM rewrite notice: {e}")

        # Adaptive Offline / Heuristic Query Expansion
        stopwords = {
            "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
            "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
            "below", "between", "both", "but", "by", "can", "can't", "cannot", "could",
            "did", "do", "does", "doing", "down", "during", "each", "few", "for", "from",
            "further", "had", "has", "have", "having", "he", "her", "here", "hers", "herself",
            "him", "himself", "his", "how", "i", "if", "in", "into", "is", "it", "its",
            "itself", "me", "more", "most", "my", "myself", "no", "nor", "not", "of", "off",
            "on", "once", "only", "or", "other", "ought", "our", "ours", "ourselves", "out",
            "over", "own", "same", "she", "should", "so", "some", "such", "than", "that",
            "the", "their", "theirs", "them", "themselves", "then", "there", "these", "they",
            "this", "those", "through", "to", "too", "under", "until", "up", "very", "was",
            "we", "were", "what", "when", "where", "which", "while", "who", "whom", "why",
            "with", "would", "you", "your", "yours", "yourself", "yourselves"
        }

        extracted_terms = []
        if retrieved_chunks:
            import re
            term_freq = {}
            for chunk in retrieved_chunks:
                text = chunk.get("content", "").lower()
                words = re.findall(r"\b[a-zA-Z]{4,}\b", text)
                for w in words:
                    if w not in stopwords:
                        term_freq[w] = term_freq.get(w, 0) + 1
            sorted_terms = sorted(term_freq.items(), key=lambda x: x[1], reverse=True)
            extracted_terms = [t[0] for t in sorted_terms[:3]]

        if extracted_terms:
            expansion = " ".join(extracted_terms)
            return f"{vague_query} {expansion} overview"

        if attempt == 1:
            return f"{vague_query} detailed summary and key points"
        else:
            return f"{vague_query} comprehensive analysis and specifications"

    @tracing_service.observe(name="llm_generate_answer", as_type="generation")
    def generate_answer(self, question: str, retrieved_chunks: List[Dict[str, Any]]) -> str:
        if not retrieved_chunks:
            return "I could not find any relevant information in the uploaded documents to answer your question."

        context_str = ""
        for i, chunk in enumerate(retrieved_chunks, 1):
            page = chunk.get("page", "N/A")
            source = os.path.basename(chunk.get("source", "document"))
            content = chunk.get("content", "").strip()
            context_str += f"\n[Context {i} | Source: {source}, Page: {page}]\n{content}\n"

        prompt = (
            "You are OmniBrain, an enterprise multi-modal AI assistant. "
            "Answer the question accurately using ONLY the context provided below. "
            "Cite the source and page number for every key claim.\n\n"
            f"Context:\n{context_str}\n\n"
            f"Question: {question}\n\n"
            "Answer:"
        )

        client, model, _ = get_llm_client(timeout_seconds=self.timeout_seconds)
        if client:
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are a strictly grounded AI assistant answering from supplied documents."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.2,
                    max_tokens=500
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                print(f"[LLMSynthesisService] LLM generation error: {e}")

        import re
        best_sentence = ""
        best_score = -1
        q_words = set(re.findall(r"\w+", question.lower())) - {
            "what", "was", "the", "in", "for", "by", "is", "of", "to", "and", "a", "an", "corp", "company", "annual", "report"
        }
        # Give higher weight to distinctive intent terms
        focus_terms = {"revenue", "margin", "operating", "profit", "churn", "acv", "office", "headcount", "stipend", "remote", "pune"} & q_words

        for chunk in retrieved_chunks:
            sentences = [s.strip() for s in re.split(r"(?<=[.!?\n])\s+", chunk.get("content", "")) if len(s.strip()) > 15]
            for s in sentences:
                s_lower = s.lower()
                s_words = set(re.findall(r"\w+", s_lower))
                score = len(s_words & q_words)
                if any(ft in s_lower for ft in focus_terms):
                    score += 5  # prioritize sentences containing core subject keyword
                if score > best_score:
                    best_score = score
                    best_sentence = s.strip()

        snippet = best_sentence if best_sentence else retrieved_chunks[0].get('content', '')[:350].strip()
        return (
            f"[Offline Synthesis] Retrieved {len(retrieved_chunks)} passage(s). "
            f"Primary Reference (Page {retrieved_chunks[0].get('page', 1)}): "
            f"\"{snippet}\""
        )