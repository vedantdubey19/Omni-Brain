import os
import base64
import mimetypes
from pathlib import Path
from typing import Dict, Any, Optional
from PIL import Image

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
    from backend.app.services.llm_client import get_vision_client
except ImportError:
    try:
        from services.llm_client import get_vision_client
    except ImportError:
        def get_vision_client(*a, **k):
            return None, None, None


class VisionAnalysisService:
    """
    Multimodal Vision Analysis Service using Gemini / GPT-4o Vision API.
    Extracts structured values, chart metrics, table data, and generates natural-language summaries.
    Provides graceful offline fallbacks when no vision-capable API key is configured.
    """

    def __init__(self, model_name: str = "gemini-2.5-flash", timeout_seconds: float = 25.0):
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.api_key = os.getenv("OPENAI_API_KEY", "")

    def is_available(self) -> bool:
        """Returns True if a valid Gemini or OpenAI API key is configured for VLM calls."""
        client, _, _ = get_vision_client()
        return client is not None

    def find_image_for_query(self, document_id: Optional[str] = None, question: Optional[str] = None) -> Optional[str]:
        """
        Locates an extracted chart/figure image matching the document or query context.
        """
        search_dirs = [
            os.path.abspath("output/images"),
            os.path.abspath("pdf_parser_module/output/images"),
            os.path.abspath("data/raw/images"),
            os.path.abspath("data/processed/images"),
            os.path.abspath("pdf_parser_module/sample_pdfs")
        ]

        # 1. Search document-scoped subfolder if document_id provided
        if document_id:
            clean_doc_stem = Path(document_id).stem
            for base_dir in search_dirs:
                if not os.path.isdir(base_dir):
                    continue
                # Exact folder match
                for cand_dir in [os.path.join(base_dir, document_id), os.path.join(base_dir, clean_doc_stem)]:
                    if os.path.isdir(cand_dir):
                        for f in sorted(os.listdir(cand_dir)):
                            if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                                return os.path.join(cand_dir, f)

        # 2. General search in extracted image directories
        for base_dir in search_dirs:
            if not os.path.isdir(base_dir):
                continue
            for root, _, files in os.walk(base_dir):
                for f in sorted(files):
                    if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                        return os.path.join(root, f)

        return None

    @tracing_service.observe(name="vision_analysis", as_type="generation")
    def analyze_image(self, image_path: str, question: str) -> Dict[str, Any]:
        """
        Sends image and natural language question to GPT-4o Vision API.
        Falls back gracefully with image inspection data if API key is not configured.
        """
        if not os.path.exists(image_path):
            return {
                "status": "IMAGE_NOT_FOUND",
                "image_path": image_path,
                "summary": f"Image artifact not found on disk at: {image_path}",
                "extracted_data": {},
                "is_fallback": False
            }

        # Inspect basic image properties
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                img_format = img.format or "PNG"
                img_mode = img.mode
        except Exception as err:
            return {
                "status": "IMAGE_READ_ERROR",
                "image_path": image_path,
                "summary": f"Failed to read image file: {str(err)}",
                "extracted_data": {},
                "is_fallback": False
            }

        # 1. VLM Inference via Gemini / OpenAI Vision if API Key is configured
        client, vlm_model, provider = get_vision_client(timeout_seconds=self.timeout_seconds)
        if client is not None:
            try:
                mime_type, _ = mimetypes.guess_type(image_path)
                if not mime_type:
                    mime_type = "image/png"

                with open(image_path, "rb") as f:
                    b64_data = base64.b64encode(f.read()).decode("utf-8")

                prompt = (
                    "You are OmniBrain Vision Agent. You specialize in visual reasoning over document figures, charts, and tables.\n"
                    f"User Question: {question}\n\n"
                    "Analyze the image thoroughly. Extract any key numerical metrics, chart axes/data points, or table values, "
                    "and provide a concise, factual natural-language summary."
                )

                response = client.chat.completions.create(
                    model=vlm_model or self.model_name,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:{mime_type};base64,{b64_data}"
                                    }
                                }
                            ]
                        }
                    ],
                    max_tokens=600,
                    temperature=0.1
                )

                vlm_summary = response.choices[0].message.content.strip()
                return {
                    "status": "COMPLETED",
                    "image_path": image_path,
                    "summary": vlm_summary,
                    "extracted_data": {
                        "dimensions": f"{width}x{height}",
                        "format": img_format,
                        "vlm_model": vlm_model or self.model_name,
                        "provider": provider
                    },
                    "is_fallback": False
                }

            except Exception as e:
                print(f"[VisionAnalysisService] VLM API call failed: {e}, falling back to metadata inspection")

        # 2. Honest Graceful Fallback for Local/Offline environments
        filename = os.path.basename(image_path)
        summary = (
            f"[Vision Analysis (Offline Mode)] Visual artifact analyzed: '{filename}' "
            f"(Dimensions: {width}x{height}, Format: {img_format}, Mode: {img_mode}). "
            "Multimodal chart/image reasoning requires an active OPENAI_API_KEY with GPT-4o vision access."
        )

        return {
            "status": "COMPLETED",
            "image_path": image_path,
            "summary": summary,
            "extracted_data": {
                "filename": filename,
                "width": width,
                "height": height,
                "format": img_format,
                "mode": img_mode
            },
            "is_fallback": True
        }
