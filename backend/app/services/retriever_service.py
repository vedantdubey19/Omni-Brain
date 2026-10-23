import os
import threading
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

# Global thread-safe reentrant lock and singleton for SentenceTransformer
_EMBEDDER_LOCK = threading.RLock()
_GLOBAL_EMBEDDER = None


class DummyFallbackEmbedder:
    """Safe fallback embedder producing 384-dim zero vectors if offline without model cache."""
    def encode(self, texts, **kwargs):
        import numpy as np
        if isinstance(texts, str):
            return np.zeros(384, dtype=np.float32)
        return np.zeros((len(texts), 384), dtype=np.float32)


def get_gemini_api_key_local() -> str:
    for k in ["GEMINI_API_KEY", "Gemini_API_KEY", "gemini_api_key"]:
        v = os.getenv(k, "").strip()
        if v and not v.startswith("your-") and not v.startswith("sk-placeholder"):
            return v
    return ""


class GeminiEmbedder:
    """Cloud-native zero-RAM embedder using Gemini embedding API."""
    def __init__(self, api_key: str):
        self.api_key = api_key

    def encode(self, texts, convert_to_numpy: bool = True, **kwargs):
        import urllib.request, json
        import numpy as np
        is_single = isinstance(texts, str)
        text_list = [texts] if is_single else list(texts)
        results = []
        for t in text_list:
            clean_t = str(t).strip()[:1500]
            if not clean_t:
                results.append([0.0] * 3072)
                continue
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={self.api_key}"
            data = json.dumps({
                "model": "models/gemini-embedding-001",
                "content": {"parts": [{"text": clean_t}]}
            }).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    res = json.loads(resp.read().decode())
                    results.append(res["embedding"]["values"])
            except Exception as e:
                print(f"[GeminiEmbedder] Notice: embedding API fallback: {e}")
                results.append([0.0] * 3072)
        arr = np.array(results, dtype=np.float32)
        return arr[0] if is_single else arr


def get_shared_embedder():
    """Thread-safe retrieval/initialization of the shared embedder singleton."""
    global _GLOBAL_EMBEDDER
    if _GLOBAL_EMBEDDER is None:
        with _EMBEDDER_LOCK:
            if _GLOBAL_EMBEDDER is None:
                g_key = get_gemini_api_key_local()
                if g_key:
                    _GLOBAL_EMBEDDER = GeminiEmbedder(g_key)
                else:
                    try:
                        from sentence_transformers import SentenceTransformer
                        _GLOBAL_EMBEDDER = SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)
                    except Exception:
                        try:
                            from sentence_transformers import SentenceTransformer
                            _GLOBAL_EMBEDDER = SentenceTransformer("all-MiniLM-L6-v2")
                        except Exception as e:
                            print(f"[RetrieverService] Notice: Model unavailable ({e}), using fallback embedder.")
                            _GLOBAL_EMBEDDER = DummyFallbackEmbedder()
    return _GLOBAL_EMBEDDER


def preload_embedder():
    """Pre-warms and loads the shared SentenceTransformer model into memory at startup."""
    return get_shared_embedder()


class RetrieverService:
    """
    Service responsible for embedding queries and searching relevant chunks from Qdrant.
    Supports local Qdrant container, Qdrant Cloud managed clusters, and in-memory fallback.
    """

    def __init__(
        self,
        collection_name: str = "omnibrain_text_chunks",
        host: Optional[str] = None,
        port: Optional[int] = None,
        url: Optional[str] = None,
        api_key: Optional[str] = None
    ):
        self.collection_name = collection_name
        qdrant_url = url or os.getenv("QDRANT_URL")
        qdrant_api_key = api_key or os.getenv("QDRANT_API_KEY")
        qdrant_host = host or os.getenv("QDRANT_HOST", "localhost")
        qdrant_port = port or int(os.getenv("QDRANT_PORT", "6333"))

        # Fallback priority: Qdrant Cloud (URL/API Key) -> Local Qdrant -> In-Memory
        try:
            if qdrant_url:
                self.client = QdrantClient(
                    url=qdrant_url,
                    api_key=qdrant_api_key,
                    timeout=5.0
                )
            else:
                self.client = QdrantClient(host=qdrant_host, port=qdrant_port, timeout=2.0)
            self.client.get_collections()
        except Exception:
            self.client = QdrantClient(location=":memory:")

        # Optional instance-level embedder override, defaults to global singleton
        self._embedder = None

    @property
    def embedder(self):
        """Thread-safe access to SentenceTransformer embedder."""
        if self._embedder is not None:
            return self._embedder
        return get_shared_embedder()

    def retrieve_relevant_chunks(
        self,
        query: str,
        top_k: int = 3,
        document_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Converts text query to vector and retrieves top-k matching points from Qdrant.
        Synchronized via _EMBEDDER_LOCK to avoid PyTorch CPU meta-tensor copy race conditions.
        """
        embedder = self.embedder
        with _EMBEDDER_LOCK:
            query_vector = embedder.encode(query, convert_to_numpy=True).tolist()

        # Optional payload filtering by specific document_id
        query_filter = None
        if document_id:
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key="source",
                        match=MatchValue(value=document_id)
                    )
                ]
            )

        try:
            if hasattr(self.client, "query_points"):
                response = self.client.query_points(
                    collection_name=self.collection_name,
                    query=query_vector,
                    limit=top_k,
                    query_filter=query_filter
                )
                search_results = response.points
            elif hasattr(self.client, "search"):
                search_results = self.client.search(
                    collection_name=self.collection_name,
                    query_vector=query_vector,
                    limit=top_k,
                    query_filter=query_filter
                )
            else:
                search_results = []
        except Exception:
            # Safe fallback if collection is not yet populated
            return []

        formatted_chunks = []
        for point in search_results:
            formatted_chunks.append({
                "chunk_id": str(point.id),
                "content": point.payload.get("content", ""),
                "page": point.payload.get("page", 1),
                "score": float(point.score),
                "source": point.payload.get("source", "unknown")
            })

        return formatted_chunks
