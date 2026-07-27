"""截图回归：Astro 构建产物（通过 http://localhost:4321 静态服务）"""
import asyncio, os
from pathlib import Path
from playwright.async_api import async_playwright

OUT = Path(__file__).resolve().parent
EDGE = r"C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=EDGE)
        ctx = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=1.5,
            color_scheme="dark",  # 默认进暗色舞台
        )
        page = await ctx.new_page()

        # 把 /playlist-poster-generator/ 前缀的请求重写到根（仅限本次截图）
        async def rewrite(route):
            url = route.request.url.replace("http://localhost:4321/playlist-poster-generator/", "http://localhost:4321/")
            await route.continue_(url=url)
        await page.route("**/playlist-poster-generator/**", rewrite)

        await page.goto("http://localhost:4321/index.html", wait_until="networkidle")
        await page.wait_for_timeout(2500)
        # 触发所有 reveal + counter（不依赖滚动）
        await page.evaluate("""
          () => {
            document.querySelectorAll('.reveal').forEach(el => el.classList.add('visible'));
            document.querySelectorAll('.roadmap-item').forEach(el => el.classList.add('visible'));
            document.querySelectorAll('.stat-num').forEach(el => {
              if (!el.dataset.animated) {
                el.dataset.animated = '1';
                el.textContent = el.dataset.count;
              }
            });
          }
        """)
        await page.wait_for_timeout(800)
        await page.screenshot(path=str(OUT/"astro-stage-dark.png"), full_page=True)
        print("✅ astro-stage-dark.png")

        # 切到画廊白
        await page.evaluate("window.gp.theme.apply('gallery','light')")
        await page.wait_for_timeout(1200)
        await page.screenshot(path=str(OUT/"astro-gallery-light.png"), full_page=True)
        print("✅ astro-gallery-light.png")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())