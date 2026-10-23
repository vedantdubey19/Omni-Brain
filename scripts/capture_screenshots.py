import os
import json
import time
import base64
import asyncio
import subprocess
import urllib.request
import websockets

SCREENSHOTS_DIR = os.path.abspath("docs/screenshots")
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

async def capture_cdp_screenshot(url: str, output_path: str, wait_seconds: int = 5, width: int = 1280, height: int = 900):
    # Start Chrome with remote debugging
    chrome_proc = subprocess.Popen([
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "--headless",
        "--disable-gpu",
        "--remote-debugging-port=9222",
        f"--window-size={width},{height}",
        "about:blank"
    ], stderr=subprocess.DEVNULL)
    time.sleep(2)

    try:
        # Get active target page
        with urllib.request.urlopen("http://localhost:9222/json") as resp:
            targets = json.loads(resp.read().decode())
            ws_url = targets[0]["webSocketDebuggerUrl"]

        async with websockets.connect(ws_url, max_size=20 * 1024 * 1024) as ws:
            # 1. Enable Page domain
            await ws.send(json.dumps({"id": 1, "method": "Page.enable"}))
            await ws.recv()

            # 2. Set viewport
            await ws.send(json.dumps({
                "id": 2,
                "method": "Emulation.setDeviceMetricsOverride",
                "params": {
                    "width": width,
                    "height": height,
                    "deviceScaleFactor": 1,
                    "mobile": False
                }
            }))
            await ws.recv()

            # 3. Navigate
            await ws.send(json.dumps({
                "id": 3,
                "method": "Page.navigate",
                "params": {"url": url}
            }))
            await ws.recv()

            # 4. Wait for page load and rendering
            await asyncio.sleep(wait_seconds)

            # 5. Capture screenshot
            await ws.send(json.dumps({
                "id": 4,
                "method": "Page.captureScreenshot",
                "params": {"format": "png"}
            }))
            while True:
                msg = await ws.recv()
                data = json.loads(msg)
                if data.get("id") == 4 and "result" in data:
                    img_b64 = data["result"]["data"]
                    with open(output_path, "wb") as f:
                        f.write(base64.b64decode(img_b64))
                    break

        print(f"Captured: {output_path} ({os.path.getsize(output_path)} bytes)")

    finally:
        chrome_proc.terminate()
        time.sleep(1)


async def main():
    # 1. React Dashboard
    print("Capturing 01_react_dashboard.png...")
    await capture_cdp_screenshot(
        "http://localhost:8501",
        os.path.join(SCREENSHOTS_DIR, "01_react_dashboard.png"),
        wait_seconds=6
    )

    # 2. FastAPI Swagger UI
    print("Capturing 02_fastapi_swagger_docs.png...")
    await capture_cdp_screenshot(
        "http://localhost:8000/docs",
        os.path.join(SCREENSHOTS_DIR, "02_fastapi_swagger_docs.png"),
        wait_seconds=4
    )

    # 3. Extracted Multimodal Chart (Copy to screenshots directory)
    src_chart = os.path.abspath("data/raw/images/chart_q4_2025.png")
    dst_chart = os.path.join(SCREENSHOTS_DIR, "03_extracted_multimodal_chart.png")
    if os.path.exists(src_chart):
        import shutil
        shutil.copyfile(src_chart, dst_chart)
        print(f"Copied chart: {dst_chart} ({os.path.getsize(dst_chart)} bytes)")

if __name__ == "__main__":
    asyncio.run(main())
