"""
渲染 4 张配色样张 PNG。
输入: swatch-template.html（带 {{占位符}}）
输出: assets/colors/{theme}-{mode}.png
"""
import asyncio
import os
import re
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "swatch-template.html"
OUT_DIR = ROOT

# 4 个状态：(data-theme, data-mode, label, 主色家族)
STATES = [
    ("dawn",     "light",  "晨光纸感 · 亮",  "ocean-green"),
    ("dawn",     "dark",   "晨光纸感 · 暗",  "ocean-green-dark"),
    ("stagedark","light",  "演出后台 · 亮",  "stage-green"),
    ("stagedark","dark",   "演出后台 · 暗",  "stage-green-dark"),
]

# 占位符替换（直接渲染十六进制，不从 CSS 变量读，避免 Playwright getComputedStyle 异步）
HEX = {
    "dawn-light": dict(
        PRIMARY_HEX="#2f8f7a", PRIMARY_STRONG_HEX="#257a67", ACCENT_HEX="#d9764f",
        BG_HEX="#f7f6f2", SURFACE1_HEX="#ffffff", SURFACE2_HEX="#eeece6",
        TEXT1_HEX="#233730", TEXT2_HEX="#5f675f", TEXT3_HEX="#8a938c",
        SUCCESS_HEX="#3d9d63", WARNING_HEX="#d9a03f", DANGER_HEX="#d05555",
        BRAND_NAME="晨光纸感", MODE_NAME="亮",
    ),
    "dawn-dark": dict(
        PRIMARY_HEX="#4dbb9e", PRIMARY_STRONG_HEX="#3da98c", ACCENT_HEX="#e89469",
        BG_HEX="#1e2c26", SURFACE1_HEX="#243630", SURFACE2_HEX="#2c3e38",
        TEXT1_HEX="#e8efeb", TEXT2_HEX="#a8b3ad", TEXT3_HEX="#6f7a74",
        SUCCESS_HEX="#5cc684", WARNING_HEX="#e8b65a", DANGER_HEX="#e57272",
        BRAND_NAME="晨光纸感", MODE_NAME="暗",
    ),
    "stagedark-light": dict(
        PRIMARY_HEX="#257a67", PRIMARY_STRONG_HEX="#1b5f50", ACCENT_HEX="#e8a33d",
        BG_HEX="#e8efeb", SURFACE1_HEX="#ffffff", SURFACE2_HEX="#d8e1dc",
        TEXT1_HEX="#15201c", TEXT2_HEX="#4d5752", TEXT3_HEX="#7d857d",
        SUCCESS_HEX="#3d9d63", WARNING_HEX="#e8a33d", DANGER_HEX="#e5645a",
        BRAND_NAME="演出后台", MODE_NAME="亮",
    ),
    "stagedark-dark": dict(
        PRIMARY_HEX="#4dbb9e", PRIMARY_STRONG_HEX="#34c78e", ACCENT_HEX="#e8a33d",
        BG_HEX="#0b0d0c", SURFACE1_HEX="#15201c", SURFACE2_HEX="#1e2c26",
        TEXT1_HEX="#e8efeb", TEXT2_HEX="#a8b3ad", TEXT3_HEX="#6f7a74",
        SUCCESS_HEX="#5cc684", WARNING_HEX="#f0b04e", DANGER_HEX="#e5645a",
        BRAND_NAME="演出后台", MODE_NAME="暗",
    ),
}


def fill_template(theme: str, mode: str, label: str) -> str:
    html = TEMPLATE.read_text(encoding="utf-8")
    key = f"{theme}-{mode}"
    h = HEX[key]
    h["THEME_LABEL"] = label
    # 把 data-theme / data-mode 也写进 html 根标签
    html = html.replace(
        f'data-theme="dawn" data-mode="light"',
        f'data-theme="{theme}" data-mode="{mode}"'
    )
    # 替换 {{KEY}} 占位符
    for k, v in h.items():
        html = html.replace("{{" + k + "}}", str(v))
    return html


# 优先本机 Chrome / Edge（playwright 自带浏览器未安装）
EDGE_PATHS = [
    r"C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    r"C:/Program Files/Google/Chrome/Application/chrome.exe",
    r"C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
]

def find_chrome():
    for p in EDGE_PATHS:
        if os.path.exists(p):
            return p
    raise RuntimeError("未找到 Chrome 或 Edge，请安装其一。")


async def main():
    chrome_path = find_chrome()
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=chrome_path)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 1024}, device_scale_factor=2)
        page = await ctx.new_page()

        for theme, mode, label, _ in STATES:
            html = fill_template(theme, mode, label)
            await page.set_content(html, wait_until="networkidle")
            await page.wait_for_timeout(150)
            slug = f"{theme}-{mode}"
            png = OUT_DIR / f"swatch-{slug}.png"
            await page.screenshot(path=str(png), full_page=True)
            print(f"✅ {png.name}  ({label})")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())