import os
import csv
import io
import random
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import fitz

TARGET_DIR = os.path.abspath("test_files")
os.makedirs(TARGET_DIR, exist_ok=True)

print(f"Generating 4 heavy test files in: {TARGET_DIR} (Total ~50 MB, each within API limits)")

# ==========================================================
# 1. HEAVY FINANCIAL CSV (SQLAgent, ~9.5 MB, 88,000 rows)
# (Within 10MB CSV upload limit)
# ==========================================================
csv_path = os.path.join(TARGET_DIR, "01_Global_Financial_Ledger_100K.csv")
print("Generating 01_Global_Financial_Ledger_100K.csv...")

regions = ["North America", "EMEA", "APAC", "Latin America"]
business_units = ["Cloud Infrastructure", "Enterprise AI", "Cybersecurity", "Fintech Solutions", "Consumer Software"]
quarters = ["Q1", "Q2", "Q3", "Q4"]
statuses = ["Finalized", "Audited", "Consolidated"]

with open(csv_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow([
        "transaction_id", "date", "fiscal_year", "quarter", "region",
        "business_unit", "revenue_millions", "cogs_millions", "operating_expenses_millions",
        "net_profit_millions", "headcount", "customer_tier", "audit_status"
    ])

    base_rev = {"2020": 25.0, "2021": 28.0, "2022": 33.0, "2023": 39.0, "2024": 45.0, "2025": 52.0}

    # 88,000 rows gives exactly ~9.5 MB, safely within the 10MB limit
    for i in range(1, 88001):
        year = str(random.choice([2020, 2021, 2022, 2023, 2024, 2025]))
        q = random.choice(quarters)
        reg = random.choice(regions)
        bu = random.choice(business_units)
        
        rev = round(base_rev[year] * random.uniform(0.7, 1.4) / 5.0, 3)
        cogs = round(rev * random.uniform(0.35, 0.45), 3)
        opex = round(rev * random.uniform(0.20, 0.30), 3)
        profit = round(rev - cogs - opex, 3)
        hc = random.randint(120, 1850)
        tier = random.choice(["Enterprise Gold", "Fortune 500", "Mid-Market", "Scale-Up"])
        status = random.choice(statuses)
        date = f"{year}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
        
        writer.writerow([
            f"TXN-{year}-{i:06d}", date, int(year), q, reg, bu,
            rev, cogs, opex, profit, hc, tier, status
        ])

csv_size_mb = os.path.getsize(csv_path) / (1024 * 1024)
print(f"✓ Created 01_Global_Financial_Ledger_100K.csv: {csv_size_mb:.2f} MB")


# ==========================================================
# 2. ULTRA-HD 4K CHART IMAGE (VisionAgent, ~12.5 MB)
# (Within 15MB Image upload limit)
# ==========================================================
jpg_path = os.path.join(TARGET_DIR, "02_UltraHD_FY2025_Executive_Revenue_Chart.jpg")
print("Generating 02_UltraHD_FY2025_Executive_Revenue_Chart.jpg...")

width, height = 3840, 2400
img = Image.new("RGB", (width, height), color="#FFF5F7")
draw = ImageDraw.Draw(img)

# Background subtle grid pattern
for x in range(0, width, 60):
    draw.line([(x, 0), (x, height)], fill="#FFE4E6", width=1)
for y in range(0, height, 60):
    draw.line([(y, 0), (width, y)], fill="#FFE4E6", width=1)

# Header banner
draw.rectangle([(120, 100), (width - 120, 300)], fill="#FFFFFF", outline="#FECDD3", width=4)
draw.text((180, 140), "AXELERO GLOBAL ENTERPRISE — FY2025 MULTI-MODAL REVENUE & PERFORMANCE DASHBOARD", fill="#E11D48")
draw.text((180, 220), "Ultra-High-Definition Visual Intelligence & Quarterly Analytics • Grounded VisionAgent Target", fill="#4C0519")

# 4 Quarterly Revenue Bars with multi-layered details
quarters_data = [
    ("Q1 2025", 42.3, "#F43F5E", (240, 500)),
    ("Q2 2025", 46.5, "#E11D48", (1100, 500)),
    ("Q3 2025", 52.5, "#BE123C", (1960, 500)),
    ("Q4 2025 (Peak)", 58.6, "#9F1239", (2820, 500))
]

max_bar_height = 900
baseline_y = 1700

for label, val, color, (bx, by) in quarters_data:
    bar_h = int((val / 65.0) * max_bar_height)
    top_y = baseline_y - bar_h
    
    # Outer card
    draw.rectangle([(bx, 420), (bx + 720, baseline_y + 200)], fill="#FFFFFF", outline="#FECDD3", width=3)
    # The bar
    draw.rectangle([(bx + 160, top_y), (bx + 560, baseline_y)], fill=color)
    
    # Labels
    draw.text((bx + 230, top_y - 70), f"${val}M", fill="#111827")
    draw.text((bx + 190, baseline_y + 40), label, fill="#374151")
    draw.text((bx + 150, baseline_y + 110), f"COGS: ${(val * 0.4):.1f}M | Margin: 60.0%", fill="#6B7280")

# KPI Summary Cards at bottom
kpis = [
    ("Total FY2025 Revenue", "$199.9M", "+28.4% YoY"),
    ("Operating Margin", "24.6%", "+380 bps"),
    ("Peak Quarter Performance", "Q4 2025 ($58.6M)", "Record High in Corporate History"),
    ("Global Enterprise Headcount", "14,820 FTEs", "+1,240 Expansion YoY")
]

for idx, (title, value, sub) in enumerate(kpis):
    kx = 120 + idx * 890
    draw.rectangle([(kx, 1960), (kx + 820, 2300)], fill="#FFFFFF", outline="#E11D48", width=3)
    draw.text((kx + 40, 1990), title, fill="#6B7280")
    draw.text((kx + 40, 2060), value, fill="#E11D48")
    draw.text((kx + 40, 2190), sub, fill="#059669")

# Add controlled high-frequency photographic grain to produce an exact ~12 MB payload
img_arr = np.array(img)
noise = np.random.randint(-14, 14, img_arr.shape, dtype='int16')
dense_arr = np.clip(img_arr + noise, 0, 255).astype('uint8')
Image.fromarray(dense_arr).save(jpg_path, format="JPEG", quality=98, subsampling=0)

jpg_size_mb = os.path.getsize(jpg_path) / (1024 * 1024)
print(f"✓ Created 02_UltraHD_FY2025_Executive_Revenue_Chart.jpg: {jpg_size_mb:.2f} MB")


# ==========================================================
# 3. HEAVY CORPORATE ANNUAL REPORT PDF (~14 MB, SearchAgent)
# ==========================================================
pdf1_path = os.path.join(TARGET_DIR, "03_Enterprise_Annual_Financial_Report_FY2025.pdf")
print("Generating 03_Enterprise_Annual_Financial_Report_FY2025.pdf...")

doc1 = fitz.open()

# We generate 12 unique uncompressed image spreads to reach ~14 MB
for page_num in range(1, 40):
    page = doc1.new_page(width=612, height=792)
    page.insert_text((54, 36), "AXELERO ENTERPRISE CORP — FY2025 ANNUAL REPORT & STRATEGIC DISCLOSURES", fontsize=8, color=(0.5, 0.1, 0.2))
    page.insert_text((530, 756), f"Page {page_num}", fontsize=8, color=(0.4, 0.4, 0.4))

    if page_num == 1:
        page.insert_text((54, 90), "EXECUTIVE SUMMARY: FISCAL YEAR 2025 RESULTS", fontsize=16, color=(0.88, 0.11, 0.28))
        body = (
            "Axelero Enterprise Corp achieved historic performance in fiscal year 2025, recording total consolidated "
            "revenue of $199.9M ($199.9 million), representing a 28.4% increase over the prior fiscal year ($155.7M).\n\n"
            "Key Financial Highlights:\n"
            "• Q1 2025 Revenue: $42.3M (compared to $27.8M in Q1 2021, achieving +52.2% multi-year expansion)\n"
            "• Q2 2025 Revenue: $46.5M\n"
            "• Q3 2025 Revenue: $52.5M\n"
            "• Q4 2025 Revenue: $58.6M (Record quarterly peak for the organization)\n"
            "• Operating Margin expanded by 380 basis points to 24.6%.\n"
            "• Global Headcount reached 14,820 FTEs across 18 specialized technical engineering facilities.\n\n"
            "SearchAgent RAG Ingestion Anchor:\n"
            "Axelero's cloud and AI revenue streams exhibited an accelerated trajectory throughout FY2025."
        )
        page.insert_textbox(fitz.Rect(54, 130, 558, 380), body, fontsize=9.5, lineheight=1.4)
    else:
        page.insert_text((54, 80), f"SECTION {page_num}: CONSOLIDATED AUDITED FINANCIAL DISCLOSURES", fontsize=11, color=(0.1, 0.1, 0.2))
        sec_text = (
            f"Detailed segmental revenue and balance sheet note for page {page_num}. Capital investments reached "
            f"${random.randint(15, 65)}.{random.randint(10, 99)} million. Total assets exceeded $620 million backed by "
            f"strong commercial reserves and liquidity buffers. Verification is provided under US GAAP compliance."
        )
        page.insert_textbox(fitz.Rect(54, 105, 558, 220), sec_text, fontsize=9, lineheight=1.35)

    # Insert a uniquely generated high-resolution exhibit on every 3rd page
    if page_num % 3 == 0 or page_num > 28:
        # Create unique noise array for each exhibit so fitz does not deduplicate streams
        ex_img = Image.new("RGB", (1400, 1800), color="#FFFFFF")
        d_ex = ImageDraw.Draw(ex_img)
        d_ex.rectangle([(20, 20), (1380, 1780)], outline="#E11D48", width=3)
        d_ex.text((50, 50), f"Exhibit {page_num}: Consolidated Statement Schedule (Page {page_num})", fill="#111827")
        
        for r_i in range(30):
            ry = 120 + r_i * 48
            d_ex.line([(50, ry), (1350, ry)], fill="#E5E7EB", width=1)
            d_ex.text((60, ry + 8), f"Line Item #{page_num*100 + r_i} — Segment Capital Distribution", fill="#4B5563")
            d_ex.text((1000, ry + 8), f"${random.randint(10, 950)}.{random.randint(10, 99)}M", fill="#0F172A")
            
        ex_noise = np.random.randint(-15, 15, (1800, 1400, 3), dtype='int16')
        unique_arr = np.clip(np.array(ex_img) + ex_noise, 0, 255).astype('uint8')
        
        ex_io = io.BytesIO()
        Image.fromarray(unique_arr).save(ex_io, format='JPEG', quality=95)
        page.insert_image(fitz.Rect(54, 230, 558, 730), stream=ex_io.getvalue())

doc1.save(pdf1_path, garbage=0, deflate=False)
doc1.close()

pdf1_size_mb = os.path.getsize(pdf1_path) / (1024 * 1024)
print(f"✓ Created 03_Enterprise_Annual_Financial_Report_FY2025.pdf: {pdf1_size_mb:.2f} MB")


# ==========================================================
# 4. HEAVY TECHNICAL WHITEPAPER PDF (~14 MB, SearchAgent)
# ==========================================================
pdf2_path = os.path.join(TARGET_DIR, "04_MultiModal_Agentic_System_Architecture.pdf")
print("Generating 04_MultiModal_Agentic_System_Architecture.pdf...")

doc2 = fitz.open()

for page_num in range(1, 19):
    page = doc2.new_page(width=612, height=792)
    page.insert_text((54, 36), "OMNIBRAIN TECHNICAL WHITEPAPER: HYBRID RETRIEVAL & AGENT TOPOLOGY", fontsize=8, color=(0.1, 0.4, 0.6))
    page.insert_text((530, 756), f"Page {page_num}", fontsize=8, color=(0.4, 0.4, 0.4))
    
    page.insert_text((54, 80), f"CHAPTER {page_num}: STATEGRAPH DIVERGENCE & VECTOR CONVERGENCE", fontsize=11, color=(0.05, 0.25, 0.45))
    tech_body = (
        f"Detailed engineering specifications for module {page_num}. OmniBrain employs a supervisor router node "
        f"that dynamically dispatches user intent to SearchAgent, SQLAgent, or VisionAgent. Dense vector embeddings "
        f"are computed via SentenceTransformers ('all-MiniLM-L6-v2') and upserted into Qdrant vector collections. "
        f"Cosine distance evaluation enforces a strict confidence threshold of 0.65 with bounded Self-RAG loops."
    )
    page.insert_textbox(fitz.Rect(54, 105, 558, 220), tech_body, fontsize=9, lineheight=1.35)

    if page_num % 2 == 0 or page_num > 10:
        tc_img = Image.new("RGB", (1400, 1800), color="#F8FAFC")
        d_tc = ImageDraw.Draw(tc_img)
        d_tc.rectangle([(20, 20), (1380, 1780)], outline="#3B82F6", width=3)
        d_tc.text((50, 50), f"Architecture Schematic Matrix {page_num}: Node Flow Latencies", fill="#0F172A")
        
        for col in range(8):
            for r in range(12):
                cx = 60 + col * 160
                cy = 120 + r * 130
                d_tc.rectangle([(cx, cy), (cx + 140, cy + 105)], fill=(random.randint(215, 235), random.randint(225, 245), random.randint(240, 255)), outline="#93C5FD", width=2)
                d_tc.text((cx + 15, cy + 35), f"{random.randint(8, 45)}ms", fill="#1E3A8A")

        tc_noise = np.random.randint(-15, 15, (1800, 1400, 3), dtype='int16')
        unique_tc = np.clip(np.array(tc_img) + tc_noise, 0, 255).astype('uint8')
        
        tc_io = io.BytesIO()
        Image.fromarray(unique_tc).save(tc_io, format='JPEG', quality=95)
        page.insert_image(fitz.Rect(54, 230, 558, 730), stream=tc_io.getvalue())

doc2.save(pdf2_path, garbage=0, deflate=False)
doc2.close()

pdf2_size_mb = os.path.getsize(pdf2_path) / (1024 * 1024)
print(f"✓ Created 04_MultiModal_Agentic_System_Architecture.pdf: {pdf2_size_mb:.2f} MB")

total_mb = csv_size_mb + jpg_size_mb + pdf1_size_mb + pdf2_size_mb
print("=" * 60)
print(f"ALL 4 HEAVY TEST FILES READY IN '{TARGET_DIR}':")
print(f"1. 01_Global_Financial_Ledger_100K.csv               : {csv_size_mb:.2f} MB")
print(f"2. 02_UltraHD_FY2025_Executive_Revenue_Chart.jpg      : {jpg_size_mb:.2f} MB")
print(f"3. 03_Enterprise_Annual_Financial_Report_FY2025.pdf   : {pdf1_size_mb:.2f} MB")
print(f"4. 04_MultiModal_Agentic_System_Architecture.pdf      : {pdf2_size_mb:.2f} MB")
print(f"------------------------------------------------------------")
print(f"TOTAL COMBINED PAYLOAD SIZE: {total_mb:.2f} MB (~50 MB Target)")
print("=" * 60)
