import os
import re
import io
import csv
import sqlite3
from typing import Dict, Any, List, Optional, Tuple, Union

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


FORBIDDEN_SQL_PATTERNS = [
    r"\b(drop|delete|update|insert|alter|create|replace|truncate)\b",
    r"\b(attach|detach|pragma|grant|revoke|vacuum|reindex)\b",
    r";"  # Prevent query stacking
]

REQUIRED_COLUMNS = ["fiscal_year", "quarter", "revenue_millions"]
COLUMN_ALIASES = {
    "year": "fiscal_year",
    "fiscal_year": "fiscal_year",
    "quarter": "quarter",
    "revenue": "revenue_millions",
    "revenue_millions": "revenue_millions",
    "cogs": "cogs_millions",
    "cogs_millions": "cogs_millions",
    "net_profit": "net_profit_millions",
    "net_profit_millions": "net_profit_millions",
    "profit": "net_profit_millions",
    "headcount": "headcount",
    "employees": "headcount",
    "employee_count": "headcount",
    "region": "region"
}


class SQLQueryService:
    """
    Structured Text-to-SQL service using local SQLite storage.
    Converts natural-language questions to safe, read-only SQL queries,
    executes them against structured financial/historical data, and synthesizes answers.
    """

    def __init__(self, db_path: Optional[str] = None, model_name: str = "gpt-4o-mini", timeout_seconds: float = 15.0):
        if db_path is None:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data"))
            os.makedirs(base_dir, exist_ok=True)
            self.db_path = os.path.join(base_dir, "omnibrain_structured.db")
        else:
            self.db_path = db_path

        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self._init_database()

    def _get_connection(self, read_only: bool = False) -> sqlite3.Connection:
        if self.db_path == ":memory:":
            if not hasattr(self, "_memory_conn") or self._memory_conn is None:
                self._memory_conn = sqlite3.connect(":memory:", check_same_thread=False, timeout=10.0)
            return self._memory_conn
        conn = sqlite3.connect(self.db_path, timeout=10.0, check_same_thread=False)
        try:
            conn.execute("PRAGMA busy_timeout=5000;")
        except Exception:
            pass
        return conn

    def _close_connection(self, conn: sqlite3.Connection):
        if self.db_path != ":memory:":
            try:
                conn.close()
            except Exception:
                pass

    def _init_database(self):
        """Initializes database schema without hardcoded dummy seed data."""
        conn = self._get_connection(read_only=False)
        try:
            try:
                conn.execute("PRAGMA journal_mode=WAL;")
            except Exception:
                pass
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS company_financials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fiscal_year INTEGER NOT NULL,
                    quarter TEXT NOT NULL,
                    revenue_millions REAL NOT NULL,
                    cogs_millions REAL,
                    net_profit_millions REAL,
                    headcount INTEGER,
                    region TEXT
                );
            """)
            conn.commit()
        finally:
            self._close_connection(conn)

        # Auto-load axelero_historical_financials.csv if available and table is empty
        if self.db_path != ":memory:" and not self.has_data():
            default_csv_candidates = [
                os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "axelero_historical_financials.csv")),
                os.path.abspath("data/axelero_historical_financials.csv"),
                os.path.abspath("axelero_historical_financials.csv")
            ]
            for csv_path in default_csv_candidates:
                if os.path.exists(csv_path):
                    try:
                        self.load_csv(csv_path)
                        print(f"[SQLQueryService] Auto-loaded {csv_path} at initialization.")
                        break
                    except Exception as e:
                        print(f"[SQLQueryService] Notice: Auto-load failed for {csv_path}: {e}")

    def has_data(self) -> bool:
        """Checks if structured company_financials dataset has records."""
        try:
            conn = self._get_connection(read_only=False)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM company_financials;")
            count = cursor.fetchone()[0]
            self._close_connection(conn)
            return count > 0
        except Exception:
            return False

    def load_csv(self, csv_source: Union[str, io.StringIO, bytes]) -> Dict[str, Any]:
        """
        Loads and replaces company_financials from a CSV source.
        Validates headers, casts types, and rejects malformed rows.
        """
        if isinstance(csv_source, bytes):
            text_stream = io.StringIO(csv_source.decode("utf-8", errors="replace"))
        elif isinstance(csv_source, str):
            if os.path.exists(csv_source):
                with open(csv_source, "r", encoding="utf-8") as f:
                    text_stream = io.StringIO(f.read())
            else:
                text_stream = io.StringIO(csv_source)
        elif isinstance(csv_source, io.StringIO):
            text_stream = csv_source
        else:
            raise ValueError("Unsupported CSV source type.")

        reader = csv.reader(text_stream)
        try:
            raw_headers = next(reader)
        except StopIteration:
            raise ValueError("CSV file is empty.")

        # Normalize and map headers
        header_map = {}
        for idx, h in enumerate(raw_headers):
            cleaned = h.strip().lower().replace(" ", "_")
            if cleaned in COLUMN_ALIASES:
                header_map[COLUMN_ALIASES[cleaned]] = idx

        missing_required = [col for col in REQUIRED_COLUMNS if col not in header_map]
        if missing_required:
            raise ValueError(
                f"CSV missing required columns: {missing_required}. "
                f"Required: fiscal_year, quarter, revenue_millions (optional: cogs_millions, net_profit_millions, headcount, region)."
            )

        parsed_rows = []
        for row_idx, row in enumerate(reader, start=2):
            if not row or all(c.strip() == "" for c in row):
                continue
            try:
                # Required: fiscal_year
                fy_val = row[header_map["fiscal_year"]].strip()
                if not fy_val:
                    raise ValueError(f"Missing fiscal_year value")
                fiscal_year = int(float(fy_val))

                # Required: quarter
                q_val = row[header_map["quarter"]].strip().upper()
                if not q_val:
                    raise ValueError(f"Missing quarter value")
                quarter = q_val

                # Required: revenue_millions
                rev_val = row[header_map["revenue_millions"]].strip()
                if not rev_val:
                    raise ValueError(f"Missing revenue_millions value")
                revenue_millions = float(rev_val)

                # Optional: cogs_millions
                cogs_millions = None
                if "cogs_millions" in header_map and len(row) > header_map["cogs_millions"]:
                    val = row[header_map["cogs_millions"]].strip()
                    if val:
                        cogs_millions = float(val)

                # Optional: net_profit_millions
                net_profit_millions = None
                if "net_profit_millions" in header_map and len(row) > header_map["net_profit_millions"]:
                    val = row[header_map["net_profit_millions"]].strip()
                    if val:
                        net_profit_millions = float(val)

                # Optional: headcount
                headcount = None
                if "headcount" in header_map and len(row) > header_map["headcount"]:
                    val = row[header_map["headcount"]].strip()
                    if val:
                        headcount = int(float(val))

                # Optional: region
                region = "Global"
                if "region" in header_map and len(row) > header_map["region"]:
                    val = row[header_map["region"]].strip()
                    if val:
                        region = val

                parsed_rows.append((
                    fiscal_year,
                    quarter,
                    revenue_millions,
                    cogs_millions,
                    net_profit_millions,
                    headcount,
                    region
                ))
            except Exception as e:
                raise ValueError(f"Row {row_idx} malformed: {str(e)}")

        if not parsed_rows:
            raise ValueError("CSV contains no valid data rows.")

        # Atomic replacement in SQLite
        conn = self._get_connection(read_only=False)
        try:
            cursor = conn.cursor()
            cursor.execute("DROP TABLE IF EXISTS company_financials;")
            cursor.execute("""
                CREATE TABLE company_financials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fiscal_year INTEGER NOT NULL,
                    quarter TEXT NOT NULL,
                    revenue_millions REAL NOT NULL,
                    cogs_millions REAL,
                    net_profit_millions REAL,
                    headcount INTEGER,
                    region TEXT
                );
            """)
            cursor.executemany("""
                INSERT INTO company_financials
                (fiscal_year, quarter, revenue_millions, cogs_millions, net_profit_millions, headcount, region)
                VALUES (?, ?, ?, ?, ?, ?, ?);
            """, parsed_rows)
            conn.commit()
        finally:
            self._close_connection(conn)

        return {
            "success": True,
            "message": f"Successfully loaded {len(parsed_rows)} rows into company_financials table.",
            "rows_loaded": len(parsed_rows),
            "columns": ["fiscal_year", "quarter", "revenue_millions", "cogs_millions", "net_profit_millions", "headcount", "region"]
        }

    def get_table_schema(self) -> str:
        """Returns the schema representation for LLM prompt context."""
        return (
            "Table: company_financials\n"
            "Columns:\n"
            "  - id: INTEGER\n"
            "  - fiscal_year: INTEGER (e.g. 2021, 2022, 2023, 2024, 2025)\n"
            "  - quarter: TEXT ('Q1', 'Q2', 'Q3', 'Q4')\n"
            "  - revenue_millions: REAL (in millions USD, e.g. 44.3)\n"
            "  - cogs_millions: REAL (cost of goods sold in millions USD)\n"
            "  - net_profit_millions: REAL (net profit in millions USD)\n"
            "  - headcount: INTEGER (number of employees, e.g. 489)\n"
            "  - region: TEXT (e.g. 'Global')"
        )

    def is_query_safe(self, sql: str) -> Tuple[bool, Optional[str]]:
        """
        Validates that SQL statement is strictly read-only and free of destructive clauses.
        """
        clean_sql = sql.strip().rstrip(";").strip()
        if not (clean_sql.lower().startswith("select") or clean_sql.lower().startswith("with")):
            return False, "Query blocked: Only SELECT statements are permitted."

        for pattern in FORBIDDEN_SQL_PATTERNS:
            if re.search(pattern, clean_sql, re.IGNORECASE):
                return False, f"Query blocked: Destructive or unauthorized SQL pattern detected ('{pattern}')."

        return True, None

    @tracing_service.observe(name="sql_generate_query", as_type="generation")
    def generate_sql(self, question: str) -> str:
        """
        Converts natural-language question to an executable SQLite query.
        Uses LLM (Gemini / OpenAI) when configured, else falls back to robust domain heuristic templates.
        """
        client, model, _ = get_llm_client(timeout_seconds=self.timeout_seconds)
        if client:
            try:
                prompt = (
                    "You are OmniBrain SQL Agent. Convert the user question into a single valid SQLite SELECT query.\n"
                    f"{self.get_table_schema()}\n\n"
                    "Rules:\n"
                    "1. Return ONLY the raw SQL query. Do not wrap in markdown or backticks.\n"
                    "2. Always query from 'company_financials'.\n"
                    "3. Use column names: fiscal_year, quarter, revenue_millions, cogs_millions, net_profit_millions, headcount, region.\n"
                    "4. Always include fiscal_year and quarter in the SELECT columns so results have complete temporal context.\n"
                    f"Question: {question}"
                )
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are a specialized Text-to-SQL converter for SQLite."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.0,
                    max_tokens=150
                )
                raw_sql = response.choices[0].message.content.strip()
                sql_match = re.search(r"```(?:sql)?\s*([\s\S]*?)```", raw_sql, re.IGNORECASE)
                if sql_match:
                    raw_sql = sql_match.group(1).strip()
                else:
                    raw_sql = re.sub(r"^```(sql)?", "", raw_sql, flags=re.IGNORECASE).strip()
                    raw_sql = re.sub(r"```$", "", raw_sql).strip()
                candidate_sql = raw_sql.rstrip(";")
                is_safe, _ = self.is_query_safe(candidate_sql)
                if is_safe:
                    return candidate_sql
            except Exception as e:
                print(f"[SQLQueryService] LLM SQL generation error: {e}, falling back to template")

        # Robust Offline / Domain Heuristic Fallback
        q = question.lower()
        years = [int(y) for y in re.findall(r"\b(20[12][0-9])\b", q)]
        quarters = [q_str.upper() for q_str in re.findall(r"\b(q[1-4])\b", q, re.IGNORECASE)]

        # 1. Headcount queries (Highest / Maximum / Employee)
        if "headcount" in q or "employee" in q or "staff" in q:
            if "highest" in q or "max" in q or "most" in q or "peak" in q:
                return "SELECT fiscal_year, quarter, headcount FROM company_financials ORDER BY headcount DESC LIMIT 1"
            if years:
                return f"SELECT fiscal_year, quarter, headcount FROM company_financials WHERE fiscal_year = {years[0]} ORDER BY quarter ASC"
            return "SELECT fiscal_year, quarter, headcount FROM company_financials ORDER BY fiscal_year ASC, quarter ASC"

        # 2. Compare across specific years (e.g. Compare Q1 2025 revenue to Q1 2021)
        if len(years) >= 2:
            y1, y2 = sorted([years[0], years[1]])
            if quarters:
                target_q = quarters[0]
                return f"SELECT fiscal_year, quarter, revenue_millions FROM company_financials WHERE (fiscal_year = {y1} AND quarter = '{target_q}') OR (fiscal_year = {y2} AND quarter = '{target_q}') ORDER BY fiscal_year ASC"
            return f"SELECT fiscal_year, quarter, revenue_millions FROM company_financials WHERE fiscal_year IN ({y1}, {y2}) ORDER BY fiscal_year ASC, quarter ASC"

        # 3. Specific quarter across all years (e.g. Show revenue for every Q3 across all years)
        if quarters and ("all" in q or "every" in q or "across" in q or not years):
            target_q = quarters[0]
            return f"SELECT fiscal_year, quarter, revenue_millions FROM company_financials WHERE quarter = '{target_q}' ORDER BY fiscal_year ASC"

        # 4. Specific year and quarter (e.g. Total revenue in Q4 2024?)
        if years and quarters:
            return f"SELECT fiscal_year, quarter, revenue_millions FROM company_financials WHERE fiscal_year = {years[0]} AND quarter = '{quarters[0]}'"

        # 5. Specific year only
        if years:
            return f"SELECT fiscal_year, quarter, revenue_millions, net_profit_millions, headcount FROM company_financials WHERE fiscal_year = {years[0]} ORDER BY quarter ASC"

        # 6. Default: All quarters revenue
        return "SELECT fiscal_year, quarter, revenue_millions FROM company_financials ORDER BY fiscal_year ASC, quarter ASC"

    def execute_sql(self, sql: str) -> Dict[str, Any]:
        """
        Safely executes read-only SQL query against local SQLite database.
        """
        is_safe, error_msg = self.is_query_safe(sql)
        if not is_safe:
            return {
                "success": False,
                "error": error_msg,
                "columns": [],
                "rows": [],
                "row_count": 0
            }

        try:
            conn = self._get_connection(read_only=True)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            columns = [col[0] for col in cursor.description] if cursor.description else []
            formatted_rows = [dict(row) for row in rows]
            self._close_connection(conn)

            return {
                "success": True,
                "columns": columns,
                "rows": formatted_rows,
                "row_count": len(formatted_rows),
                "error": None
            }
        except sqlite3.Error as e:
            print(f"[SQLQueryService] SQLite execution error: {e}")
            return {
                "success": False,
                "error": f"SQL syntax or execution error: {str(e)}",
                "columns": [],
                "rows": [],
                "row_count": 0
            }

    @tracing_service.observe(name="sql_synthesize_answer", as_type="generation")
    def synthesize_answer(self, question: str, sql: str, query_result: Dict[str, Any]) -> str:
        """
        Synthesizes natural-language answer from executed SQL and resulting rows.
        """
        if not query_result.get("success"):
            return f"Unable to execute SQL query: {query_result.get('error')}"

        rows = query_result.get("rows", [])
        if not rows:
            return f"SQL query executed successfully (`{sql}`), but returned 0 records."

        client, model, _ = get_llm_client(timeout_seconds=self.timeout_seconds)
        if client:
            try:
                prompt = (
                    "You are OmniBrain SQL Agent. Formulate a concise, factual answer to the user's question "
                    "using the structured query results below. Include exact figures, units, and always explicitly state both the quarter and fiscal year (e.g. 'Q4 2025') if present in the results.\n\n"
                    f"User Question: {question}\n"
                    f"Executed SQL: {sql}\n"
                    f"Results: {rows}\n\n"
                    "Answer:"
                )
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are a quantitative financial analyst answering from structured SQLite data."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    max_tokens=250
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                print(f"[SQLQueryService] LLM synthesis error: {e}")

        # Structured Offline Answer Formulation
        summary_sentence = ""
        q_lower = question.lower()
        if len(rows) == 1:
            r = rows[0]
            if "headcount" in r and ("highest" in q_lower or "max" in q_lower or "peak" in q_lower):
                summary_sentence = f"The highest headcount recorded was {r['headcount']} in {r.get('quarter', '')} {r.get('fiscal_year', '')}."
            elif "revenue_millions" in r:
                summary_sentence = f"Total revenue in {r.get('quarter', '')} {r.get('fiscal_year', '')} was ${r['revenue_millions']}M."
        elif len(rows) == 2 and "compare" in q_lower and "revenue_millions" in rows[0]:
            r1, r2 = rows[0], rows[1]
            summary_sentence = (
                f"Comparison: {r1.get('quarter', '')} {r1.get('fiscal_year', '')} revenue was ${r1['revenue_millions']}M "
                f"vs {r2.get('quarter', '')} {r2.get('fiscal_year', '')} revenue of ${r2['revenue_millions']}M."
            )

        lines = []
        if summary_sentence:
            lines.append(summary_sentence)
            lines.append("")

        lines.append(f"**Structured SQL Query Results** (`{sql}`):")
        for row in rows:
            row_parts = []
            for k, v in row.items():
                if isinstance(v, float) and "margin" in k:
                    row_parts.append(f"{k}: {v*100:.1f}%")
                elif isinstance(v, float) and ("revenue" in k or "profit" in k or "cogs" in k):
                    row_parts.append(f"{k}: ${v:.1f}M")
                else:
                    row_parts.append(f"{k}: {v}")
            lines.append(f"- {', '.join(row_parts)}")

        return "\n".join(lines)

    @tracing_service.observe(name="sql_agent_query")
    def query(self, question: str) -> Dict[str, Any]:
        """
        End-to-end Text-to-SQL entry point: checks dataset presence, generates SQL, executes safely, and synthesizes answer.
        """
        if not self.has_data():
            return {
                "question": question,
                "executed_sql": None,
                "success": False,
                "columns": [],
                "rows": [],
                "row_count": 0,
                "error": "No structured dataset is loaded",
                "answer": "No structured dataset is loaded",
                "status": "NO_DATA"
            }

        sql = self.generate_sql(question)
        result = self.execute_sql(sql)
        answer = self.synthesize_answer(question, sql, result)

        return {
            "question": question,
            "executed_sql": sql,
            "success": result["success"],
            "columns": result["columns"],
            "rows": result["rows"],
            "row_count": result["row_count"],
            "error": result["error"],
            "answer": answer,
            "status": "COMPLETED" if result["success"] else "SQL_ERROR"
        }
