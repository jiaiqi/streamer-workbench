"""渲染落地页截图：暗色舞台-dark + 画廊白-light"""
import asyncio, os, sys
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent  # project root
HTML = ROOT / "site" / "landing" / "index.html"
OUT = Path(__file__).resolve().parent  # same dir as this script

EDGE = r"C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
if not os.path.exists(EDGE):
    EDGE = r"C:/Program Files/Google/Chrome/Application/chrome.exe"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=EDGE)
        ctx = await browser.new_context(viewport={"width":1440,"height":900}, device_scale_factor=1.5)
        page = await ctx.new_page()
        abs_url = "file:///" + str(HTML).replace("\\","/")
        await page.goto(abs_url, wait_until="networkidle")
        await page.wait_for_timeout(2000)

        # 截图 1：暗色舞台 dark（默认）
        await page.screenshot(path=str(OUT/"landing-stage-dark.png"), full_page=True)
        print("✅ landing-stage-dark.png")

        # 切换到画廊白 light
        await page.evaluate("""() => {
            document.documentElement.setAttribute('data-brand','gallery');
            document.documentElement.setAttribute('data-mode','light');
            document.getElementById('brand-label').textContent = '画廊白';
            document.getElementById('mode-btn').textContent = '☀';
        }""")
        await page.wait_for_timeout(1200)
        await page.screenshot(path=str(OUT/"landing-gallery-light.png"), full_page=True)
        print("✅ landing-gallery-light.png")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())