"""
End-to-End Safe Demo Verification Script
Tests:
1. Document upload & indexing of OmniBrain_Demo_Report.pdf
2. Search question -> SearchAgent ($199.9M)
3. SQL question -> SQLAgent ($42.3M vs $27.8M)
4. Joke request -> Blocked by Guardrails
5. Vague query -> Self-RAG query refinement / retry
6. Second document upload (HR Policy) -> Document isolation verified
"""
import os
import sys
import time
import requests

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

def print_box(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)

def main():
    print_box("1. Health Check")
    h = requests.get(f"{BACKEND_URL}/health").json()
    print("Health response:", h)
    assert h.get("status") == "healthy"

    print_box("2. Upload First Document (OmniBrain_Demo_Report.pdf)")
    with open("OmniBrain_Demo_Report.pdf", "rb") as f:
        resp = requests.post(
            f"{BACKEND_URL}/api/v1/upload",
            files={"file": ("OmniBrain_Demo_Report.pdf", f, "application/pdf")}
        )
    assert resp.status_code == 201, f"Upload failed: {resp.text}"
    job_1 = resp.json()["job_id"]
    print(f"Uploaded OmniBrain_Demo_Report.pdf, job_id: {job_1}")

    # Wait for completion
    for _ in range(30):
        st = requests.get(f"{BACKEND_URL}/api/v1/ingest/status/{job_1}").json()
        if st["status"] == "COMPLETED":
            print("Ingestion COMPLETED in job_1")
            break
        time.sleep(1)

    print_box("3. Search Question (Document Semantic Retrieval)")
    q1 = "What was Axelero Demo Corp's total revenue in fiscal year 2025?"
    r1 = requests.post(
        f"{BACKEND_URL}/api/v1/agent/query",
        json={"question": q1, "session_id": "demo-safe-session", "document_id": "OmniBrain_Demo_Report.pdf"}
    ).json()
    print("Question:", q1)
    print("Routed Agent:", r1["routed_agent"])
    print("Answer snippet:", r1["final_answer"][:150])
    assert r1["routed_agent"] == "SearchAgent"
    assert "199.9" in r1["final_answer"]

    print_box("4. SQL Question (Structured SQLite Comparison)")
    q2 = "Compare Q1 2025 revenue to Q1 2021"
    r2 = requests.post(
        f"{BACKEND_URL}/api/v1/agent/query",
        json={"question": q2, "session_id": "demo-safe-session", "document_id": "OmniBrain_Demo_Report.pdf"}
    ).json()
    print("Question:", q2)
    print("Routed Agent:", r2["routed_agent"])
    print("Executed SQL:", r2.get("executed_sql"))
    print("SQL Results:", r2.get("sql_results"))
    print("Final Answer:", r2.get("final_answer"))
    assert r2["routed_agent"] == "SQLAgent"
    assert "42.3" in r2["final_answer"]
    assert "27.8" in r2["final_answer"]

    print_box("5. Joke Request (Safety Guardrails Enforcement)")
    q3 = "tell me a funny joke"
    r3 = requests.post(
        f"{BACKEND_URL}/api/v1/query",
        json={"question": q3, "top_k": 2}
    ).json()
    print("Question:", q3)
    print("Status:", r3["status"])
    print("Answer:", r3["answer"])
    assert r3["status"] == "BLOCKED_BY_GUARDRAILS"

    print_box("6. Vague Query (Self-RAG Retry & Query Refinement)")
    q4 = "Tell me about the subsidiary in Germany"
    r4 = requests.post(
        f"{BACKEND_URL}/api/v1/query",
        json={"question": q4, "top_k": 3}
    ).json()
    print("Question:", q4)
    print("Retried:", r4.get("retried"))
    print("Retry Count:", r4.get("retry_count"))
    print("Low Confidence Flag:", r4.get("low_confidence"))
    assert r4.get("retried") is True
    assert r4.get("retry_count") >= 1

    print_box("7. Upload Second Document & Verify Isolation")
    with open("OmniBrain_Demo_SecondDoc_HR_Policy.pdf", "rb") as f:
        resp2 = requests.post(
            f"{BACKEND_URL}/api/v1/upload",
            files={"file": ("OmniBrain_Demo_SecondDoc_HR_Policy.pdf", f, "application/pdf")}
        )
    assert resp2.status_code == 201
    job_2 = resp2.json()["job_id"]
    for _ in range(30):
        st2 = requests.get(f"{BACKEND_URL}/api/v1/ingest/status/{job_2}").json()
        if st2["status"] == "COMPLETED":
            print("Ingestion COMPLETED in job_2 (HR Policy)")
            break
        time.sleep(1)

    # Scoped to Doc 2: HR stipend question
    r_hr = requests.post(
        f"{BACKEND_URL}/api/v1/agent/query",
        json={"question": "What is the remote work stipend amount?", "document_id": "OmniBrain_Demo_SecondDoc_HR_Policy.pdf"}
    ).json()
    print("HR Query routed to:", r_hr["routed_agent"])
    print("HR Answer:", r_hr["final_answer"][:150])
    for src in r_hr.get("referenced_sources", []):
        assert src["source"] == "OmniBrain_Demo_SecondDoc_HR_Policy.pdf"

    # Scoped to Doc 1: Financial query returns no HR Policy content
    r_fin = requests.post(
        f"{BACKEND_URL}/api/v1/agent/query",
        json={"question": "What is the operating margin improvement?", "document_id": "OmniBrain_Demo_Report.pdf"}
    ).json()
    print("Fin Query routed to:", r_fin["routed_agent"])
    for src in r_fin.get("referenced_sources", []):
        assert src["source"] == "OmniBrain_Demo_Report.pdf"

    print_box("🎉 ALL END-TO-END DEMO CHECKS PASSED WITH FULL ISOLATION!")

if __name__ == "__main__":
    main()
