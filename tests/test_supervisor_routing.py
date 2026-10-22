import io
import fitz
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_supervisor_e2e_real_search_pipeline():
    """
    End-to-End Test:
    1. Uploads a real PDF document via /api/v1/upload.
    2. Polls /api/v1/ingest/status/{job_id} until COMPLETED.
    3. Queries /api/v1/agent/query and asserts:
       - Real routing to SearchAgent.
       - Real vector retrieval with sources matching the uploaded document (not fake sample.pdf).
       - Real LLM answer synthesis without placeholder strings.
    """
    # 1. Create a genuine PDF document with target facts
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (50, 50),
        "OmniBrain Enterprise Report: The annual revenue growth rate reached 28.5 percent in FY2025."
    )
    pdf_bytes = doc.tobytes()

    filename = "e2e_verified_report.pdf"

    # 2. Upload the PDF
    upload_resp = client.post(
        "/api/v1/upload",
        files={"file": (filename, io.BytesIO(pdf_bytes), "application/pdf")}
    )
    assert upload_resp.status_code == 201, f"Upload failed: {upload_resp.text}"
    upload_data = upload_resp.json()
    job_id = upload_data["job_id"]
    assert upload_data["filename"] == filename

    # 3. Check / Poll ingestion status
    status_resp = client.get(f"/api/v1/ingest/status/{job_id}")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["status"] == "COMPLETED", f"Ingestion failed: {status_data.get('message')}"

    # 4. Execute multi-agent supervisor query against uploaded document
    query_payload = {
        "question": "What is the annual revenue growth rate?",
        "session_id": "test-session-e2e-real",
        "document_id": filename
    }
    response = client.post("/api/v1/agent/query", json=query_payload)
    assert response.status_code == 200, f"Query failed: {response.text}"
    data = response.json()

    # Assert real Supervisor dynamic routing
    assert data["routed_agent"] == "SearchAgent"
    assert any(step["agent_name"] == "SupervisorAgent" for step in data["execution_steps"])
    assert any(step["agent_name"] == "SearchAgent" for step in data["execution_steps"])

    # Assert real retrieved chunks with genuine source metadata (not mock sample.pdf)
    assert len(data["referenced_sources"]) > 0, "No chunks were retrieved from vector store."
    for source in data["referenced_sources"]:
        assert source["source"] == filename, f"Expected source {filename}, got {source['source']}"
        assert "revenue growth rate" in source.get("content", "").lower()

    # Assert real synthesized final answer
    assert len(data["final_answer"]) > 0
    assert "[Search Agent Response] Retrieved contextual passages" not in data["final_answer"], "Found old canned response!"
    assert data["status"] == "COMPLETED"


def test_supervisor_routes_to_vision_agent():
    """
    Image/chart queries must route to VisionAgent and execute multimodal analysis.
    """
    payload = {
        "question": "Explain the revenue breakdown bar chart and visual plot on page 4.",
        "session_id": "test-session-vision"
    }
    response = client.post("/api/v1/agent/query", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["routed_agent"] == "VisionAgent"
    assert any(step["agent_name"] == "VisionAgent" for step in data["execution_steps"])
    assert data["status"] == "COMPLETED"
    assert len(data["final_answer"]) > 0


def test_supervisor_graceful_handling_on_empty_context():
    """
    Queries with no matching document context should be handled gracefully without crashing.
    """
    payload = {
        "question": "What was the total revenue recorded in the 1999 fiscal year report?",
        "session_id": "test-session-irrelevant",
        "document_id": "non_existent_doc.pdf"
    }
    response = client.post("/api/v1/agent/query", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["routed_agent"] == "SearchAgent"
    assert len(data["referenced_sources"]) == 0
    assert "could not find any relevant information" in data["final_answer"].lower() or "offline synthesis" in data["final_answer"].lower()


def test_supervisor_mixed_signal_query_routing():
    """
    Boundary Case 1: Mixed-signal query containing both visual keywords and text-retrieval intent.
    Example: 'Summarize the revenue figures and also describe the chart on page 3'
    Prioritizes visual reasoning capabilities whenever visual modalities are requested.
    """
    payload = {
        "question": "Summarize the revenue figures and also describe the chart on page 3.",
        "session_id": "test-session-mixed-signal"
    }
    response = client.post("/api/v1/agent/query", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["routed_agent"] == "VisionAgent"
    assert any(step["agent_name"] == "VisionAgent" for step in data["execution_steps"])
    assert data["status"] == "COMPLETED"
    assert len(data["final_answer"]) > 0


def test_supervisor_near_miss_visual_query_routing():
    """
    Boundary Case 2: Near-miss visual query with visually-adjacent vocabulary not in the static keyword list.
    Example: 'What does the illustration on page 2 show?'
    """
    payload = {
        "question": "What does the illustration on page 2 show?",
        "session_id": "test-session-near-miss"
    }
    response = client.post("/api/v1/agent/query", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["routed_agent"] == "SearchAgent"
    assert any(step["agent_name"] == "SearchAgent" for step in data["execution_steps"])


def test_supervisor_case_insensitive_routing():
    """
    Boundary Case 3: Case sensitivity check.
    Ensures keyword matching correctly handles uppercase, lowercase, and mixed-case queries.
    """
    payload = {
        "question": "Show me the CHART and visual PLOT on page 5.",
        "session_id": "test-session-case-insensitive"
    }
    response = client.post("/api/v1/agent/query", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["routed_agent"] == "VisionAgent"
    assert any(step["agent_name"] == "VisionAgent" for step in data["execution_steps"])
    assert data["status"] == "COMPLETED"
    assert len(data["final_answer"]) > 0


def test_supervisor_vision_agent_with_real_image():
    """
    Validates end-to-end VisionAgent analysis on an actual chart image.
    Asserts multimodal analysis execution step, status COMPLETED, and extracted properties.
    """
    import os
    from PIL import Image, ImageDraw

    test_img_dir = os.path.abspath("output/images/chart_test_report.pdf")
    os.makedirs(test_img_dir, exist_ok=True)
    test_img_path = os.path.join(test_img_dir, "page_1_image_0.png")

    img = Image.new("RGB", (300, 200), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, 280, 180], outline=(0, 0, 0), width=2)
    draw.rectangle([50, 80, 100, 180], fill=(50, 120, 220))
    draw.rectangle([130, 40, 180, 180], fill=(50, 120, 220))
    draw.rectangle([210, 110, 260, 180], fill=(50, 120, 220))
    img.save(test_img_path)

    payload = {
        "question": "What does the bar chart show for quarterly growth?",
        "session_id": "test-session-vlm-chart",
        "document_id": "chart_test_report.pdf"
    }
    response = client.post("/api/v1/agent/query", json=payload)
    assert response.status_code == 200, f"Query failed: {response.text}"
    data = response.json()

    assert data["routed_agent"] == "VisionAgent"
    assert data["status"] == "COMPLETED"
    assert any(
        step["agent_name"] == "VisionAgent" and step["action_taken"] == "VLM_MULTIMODAL_ANALYSIS"
        for step in data["execution_steps"]
    )
    assert len(data["final_answer"]) > 0
    assert "chart" in data["final_answer"].lower() or "page_1_image_0.png" in data["final_answer"] or "300x200" in data["final_answer"] or "quarterly" in data["final_answer"].lower()


def test_supervisor_routes_to_sql_agent_historical_query():
    """
    Historical / structured queries must route to SQLAgent and return real SQLite data.
    """
    payload = {
        "question": "What is the historical revenue trend from 2021 to 2025?",
        "session_id": "test-session-sql-historical"
    }
    response = client.post("/api/v1/agent/query", json=payload)
    assert response.status_code == 200, f"Query failed: {response.text}"
    data = response.json()

    assert data["routed_agent"] == "SQLAgent"
    assert any(step["agent_name"] == "SupervisorAgent" for step in data["execution_steps"])
    assert any(step["agent_name"] == "SQLAgent" for step in data["execution_steps"])
    assert data["status"] == "COMPLETED"
    assert data.get("executed_sql") is not None
    assert data["executed_sql"].lower().startswith("select")
    assert "company_financials" in data["executed_sql"]
    assert "2021" in data["final_answer"]
    assert "2025" in data["final_answer"]


def test_supervisor_routes_to_sql_agent_numeric_how_much_query():
    """
    'How much' quantitative questions must route to SQLAgent.
    """
    payload = {
        "question": "How much was the net profit in 2023?",
        "session_id": "test-session-sql-numeric"
    }
    response = client.post("/api/v1/agent/query", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["routed_agent"] == "SQLAgent"
    assert any(step["agent_name"] == "SQLAgent" for step in data["execution_steps"])
    assert data["status"] == "COMPLETED"
    assert data.get("executed_sql") is not None
    assert "32.1" in data["final_answer"] or "profit" in data["final_answer"].lower()


def test_supervisor_sql_agent_injection_safety():
    """
    Validates that destructive SQL injection attempts and non-SELECT queries are safely rejected.
    """
    from backend.app.services.sql_service import SQLQueryService
    sql_svc = SQLQueryService()

    destructive_queries = [
        "DROP TABLE company_financials",
        "DELETE FROM company_financials WHERE year = 2021",
        "UPDATE company_financials SET revenue = 9999",
        "INSERT INTO company_financials (company, year, quarter, revenue, net_profit, operating_expenses, gross_margin, headcount) VALUES ('EvilCorp', 2026, 'FY', 0, 0, 0, 0, 0)",
        "SELECT * FROM company_financials; DROP TABLE company_financials;",
        "ALTER TABLE company_financials ADD COLUMN backdoor TEXT",
        "ATTACH DATABASE 'evil.db' AS evil"
    ]

    for malicious_sql in destructive_queries:
        is_safe, error = sql_svc.is_query_safe(malicious_sql)
        assert not is_safe, f"Expected unsafe query to be rejected: {malicious_sql}"
        assert error is not None

        result = sql_svc.execute_sql(malicious_sql)
        assert result["success"] is False
        assert "blocked" in result["error"].lower() or "syntax" in result["error"].lower()


def test_supervisor_search_queries_still_route_to_search_agent():
    """
    Verifies that semantic document queries without SQL/visual intent continue routing to SearchAgent.
    """
    payload = {
        "question": "Explain the general mission statement and platform capabilities.",
        "session_id": "test-session-search-fallback"
    }
    response = client.post("/api/v1/agent/query", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["routed_agent"] == "SearchAgent"
    assert any(step["agent_name"] == "SearchAgent" for step in data["execution_steps"])


def test_supervisor_regression_fix1_routing():
    """
    Regression test suite for Fix 1 routing with active demo PDF:
    - 'What was Axelero Demo Corp\'s total revenue in fiscal year 2025?' -> SearchAgent, $199.9M
    - 'How much did operating margin improve by?' -> SearchAgent, 14.2% to 17.6%
    - 'What is the customer churn rate?' -> SearchAgent, 6.8% to 4.9%
    - 'Compare Q1 2025 revenue to Q1 2021' -> SQLAgent, $42.3M vs $27.8M
    - 'What was the highest headcount recorded?' -> SQLAgent
    - 'What does the chart show?' -> VisionAgent
    """
    # 1. Total revenue in fiscal year 2025 with active document -> SearchAgent, $199.9M
    p1 = {
        "question": "What was Axelero Demo Corp's total revenue in fiscal year 2025?",
        "session_id": "reg-test-1",
        "document_id": "OmniBrain_Demo_Report.pdf"
    }
    r1 = client.post("/api/v1/agent/query", json=p1)
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["routed_agent"] == "SearchAgent"
    assert "199.9" in d1["final_answer"]

    # 2. Operating margin improvement -> SearchAgent, 14.2% to 17.6%
    p2 = {
        "question": "How much did operating margin improve by?",
        "session_id": "reg-test-2",
        "document_id": "OmniBrain_Demo_Report.pdf"
    }
    r2 = client.post("/api/v1/agent/query", json=p2)
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["routed_agent"] == "SearchAgent"
    assert "14.2" in d2["final_answer"]
    assert "17.6" in d2["final_answer"]

    # 3. Customer churn rate -> SearchAgent, 6.8% to 4.9%
    p3 = {
        "question": "What is the customer churn rate?",
        "session_id": "reg-test-3",
        "document_id": "OmniBrain_Demo_Report.pdf"
    }
    r3 = client.post("/api/v1/agent/query", json=p3)
    assert r3.status_code == 200
    d3 = r3.json()
    assert d3["routed_agent"] == "SearchAgent"
    assert "6.8" in d3["final_answer"]
    assert "4.9" in d3["final_answer"]

    # 4. Compare Q1 2025 revenue to Q1 2021 with active document -> SQLAgent, $42.3M vs $27.8M
    p4 = {
        "question": "Compare Q1 2025 revenue to Q1 2021",
        "session_id": "reg-test-4",
        "document_id": "OmniBrain_Demo_Report.pdf"
    }
    r4 = client.post("/api/v1/agent/query", json=p4)
    assert r4.status_code == 200
    d4 = r4.json()
    assert d4["routed_agent"] == "SQLAgent"
    assert "42.3" in d4["final_answer"]
    assert "27.8" in d4["final_answer"]

    # 5. What was the highest headcount recorded? -> SQLAgent
    p5 = {
        "question": "What was the highest headcount recorded?",
        "session_id": "reg-test-5"
    }
    r5 = client.post("/api/v1/agent/query", json=p5)
    assert r5.status_code == 200
    d5 = r5.json()
    assert d5["routed_agent"] == "SQLAgent"

    # 6. What does the chart show? -> VisionAgent
    p6 = {
        "question": "What does the chart show?",
        "session_id": "reg-test-6"
    }
    r6 = client.post("/api/v1/agent/query", json=p6)
    assert r6.status_code == 200
    d6 = r6.json()
    assert d6["routed_agent"] == "VisionAgent"
