import os
import io
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.sql_service import SQLQueryService

client = TestClient(app)

SAMPLE_CSV = """fiscal_year,quarter,revenue_millions,cogs_millions,net_profit_millions,headcount,region
2021,Q1,27.8,16.6,3.1,210,Global
2021,Q2,29.4,17.5,3.4,225,Global
2021,Q3,31.2,18.2,3.7,240,Global
2021,Q4,33.5,19.5,4.2,260,Global
2022,Q1,34.2,20.0,4.5,280,Global
2022,Q2,35.0,20.4,4.8,300,Global
2022,Q3,35.4,20.8,5.0,320,Global
2022,Q4,37.8,21.8,5.4,340,Global
2023,Q1,38.0,21.9,5.5,350,Global
2023,Q2,38.5,22.0,5.7,355,Global
2023,Q3,39.5,22.3,6.0,358,Global
2023,Q4,40.0,22.5,6.2,360,Global
2024,Q1,38.2,22.0,5.0,360,Global
2024,Q2,40.1,22.8,5.4,380,Global
2024,Q3,43.5,23.5,5.8,400,Global
2024,Q4,44.3,24.5,6.2,415,Global
2025,Q1,42.3,23.2,6.0,420,Global
2025,Q2,46.5,24.8,7.0,445,Global
2025,Q3,51.2,26.5,8.2,468,Global
2025,Q4,58.6,29.5,10.3,489,Global
"""


def test_sql_service_load_csv_and_validate():
    """Verify CSV loader parses rows and columns correctly into SQLite."""
    svc = SQLQueryService(db_path=":memory:")
    res = svc.load_csv(SAMPLE_CSV)
    assert res["success"] is True
    assert res["rows_loaded"] == 20
    assert svc.has_data() is True


def test_sql_service_rejects_missing_headers():
    """Missing required columns must raise a ValueError."""
    bad_csv = "year,notes\n2021,some note"
    svc = SQLQueryService(db_path=":memory:")
    with pytest.raises(ValueError) as exc:
        svc.load_csv(bad_csv)
    assert "missing required columns" in str(exc.value).lower()


def test_sql_service_rejects_malformed_rows():
    """Malformed row with non-numeric revenue must be rejected."""
    bad_csv = """fiscal_year,quarter,revenue_millions,headcount
2021,Q1,NOT_A_NUMBER,210
"""
    svc = SQLQueryService(db_path=":memory:")
    with pytest.raises(ValueError) as exc:
        svc.load_csv(bad_csv)
    assert "malformed" in str(exc.value).lower()


def test_sql_service_empty_dataset_handling():
    """When no data is loaded, service must state 'No structured dataset is loaded'."""
    svc = SQLQueryService(db_path=":memory:")
    # Database is empty in-memory
    result = svc.query("What was the revenue in Q4 2024?")
    assert result["status"] == "NO_DATA"
    assert "No structured dataset is loaded" in result["answer"]


def test_sql_service_safety_and_read_only():
    """SQL validator must block all destructive statements and stacked queries."""
    svc = SQLQueryService(db_path=":memory:")
    svc.load_csv(SAMPLE_CSV)

    # Test DROP TABLE
    safe, err = svc.is_query_safe("DROP TABLE company_financials;")
    assert safe is False
    assert "Only SELECT statements are permitted" in err or "Destructive" in err

    # Test DELETE
    safe, err = svc.is_query_safe("DELETE FROM company_financials WHERE fiscal_year = 2021;")
    assert safe is False

    # Test UPDATE
    safe, err = svc.is_query_safe("UPDATE company_financials SET revenue_millions = 999;")
    assert safe is False

    # Test stacked multi-statement injection
    safe, err = svc.is_query_safe("SELECT * FROM company_financials; DROP TABLE company_financials;")
    assert safe is False

    # Executing an unsafe query directly through execute_sql returns error
    exec_res = svc.execute_sql("DROP TABLE company_financials;")
    assert exec_res["success"] is False
    assert exec_res["error"] is not None


def test_sql_load_csv_api_endpoint():
    """POST /api/v1/sql/load-csv must upload and load CSV, rejecting non-csv."""
    # 1. Reject non-csv upload
    non_csv_resp = client.post(
        "/api/v1/sql/load-csv",
        files={"file": ("report.pdf", b"fake pdf bytes", "application/pdf")}
    )
    assert non_csv_resp.status_code == 400
    assert "Only .csv files are supported" in non_csv_resp.json()["detail"]

    # 2. Upload valid CSV
    csv_bytes = SAMPLE_CSV.encode("utf-8")
    resp = client.post(
        "/api/v1/sql/load-csv",
        files={"file": ("axelero_historical_financials.csv", io.BytesIO(csv_bytes), "text/csv")}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["rows_loaded"] == 20


def test_sql_agent_queries_with_real_csv():
    """
    Test real CSV queries via /api/v1/agent/query:
    - 'Total revenue in Q4 2024?' -> 44.3, routed to SQLAgent
    - 'Compare Q1 2025 revenue to Q1 2021' -> 42.3 vs 27.8, routed to SQLAgent
    - 'Highest headcount recorded and in which quarter?' -> 489, Q4 2025, routed to SQLAgent
    - 'Show revenue for every Q3 across all years' -> 5 rows, routed to SQLAgent
    """
    # 1. Total revenue in Q4 2024?
    q1 = client.post("/api/v1/agent/query", json={
        "question": "Total revenue in Q4 2024?",
        "session_id": "test-sql-q1"
    })
    assert q1.status_code == 200
    d1 = q1.json()
    assert d1["routed_agent"] == "SQLAgent"
    assert "44.3" in d1["final_answer"]

    # 2. Compare Q1 2025 revenue to Q1 2021
    q2 = client.post("/api/v1/agent/query", json={
        "question": "Compare Q1 2025 revenue to Q1 2021",
        "session_id": "test-sql-q2"
    })
    assert q2.status_code == 200
    d2 = q2.json()
    assert d2["routed_agent"] == "SQLAgent"
    assert "42.3" in d2["final_answer"]
    assert "27.8" in d2["final_answer"]

    # 3. Highest headcount recorded and in which quarter?
    q3 = client.post("/api/v1/agent/query", json={
        "question": "Highest headcount recorded and in which quarter?",
        "session_id": "test-sql-q3"
    })
    assert q3.status_code == 200
    d3 = q3.json()
    assert d3["routed_agent"] == "SQLAgent"
    assert "489" in d3["final_answer"]
    assert "Q4" in d3["final_answer"]
    assert "2025" in d3["final_answer"]

    # 4. Show revenue for every Q3 across all years
    q4 = client.post("/api/v1/agent/query", json={
        "question": "Show revenue for every Q3 across all years",
        "session_id": "test-sql-q4"
    })
    assert q4.status_code == 200
    d4 = q4.json()
    assert d4["routed_agent"] == "SQLAgent"
    assert len(d4["sql_results"]) == 5

    # Assert all five expected Q3 revenue values: 2021 31.2, 2022 35.4, 2023 39.5, 2024 43.5, 2025 51.2
    q3_rows = {row["fiscal_year"]: row["revenue_millions"] for row in d4["sql_results"]}
    assert q3_rows[2021] == 31.2
    assert q3_rows[2022] == 35.4
    assert q3_rows[2023] == 39.5
    assert q3_rows[2024] == 43.5
    assert q3_rows[2025] == 51.2


def test_sql_dataset_total_row_count_and_q3_2025():
    """
    Assert that the loaded axelero_historical_financials dataset has exactly 20 rows,
    and that Q3 2025 revenue equals 51.2.
    """
    from backend.app.agents.supervisor import get_sql_service
    svc = get_sql_service()
    assert svc is not None
    conn = svc._get_connection(read_only=True)
    cursor = conn.cursor()

    # Total row count must be 20
    cursor.execute("SELECT COUNT(*) FROM company_financials;")
    count = cursor.fetchone()[0]
    assert count == 20, f"Expected 20 rows, got {count}"

    # Q3 2025 revenue must equal 51.2
    cursor.execute("SELECT revenue_millions FROM company_financials WHERE fiscal_year = 2025 AND quarter = 'Q3';")
    q3_2025_rev = cursor.fetchone()[0]
    assert q3_2025_rev == 51.2, f"Expected Q3 2025 revenue to be 51.2, got {q3_2025_rev}"
    svc._close_connection(conn)
