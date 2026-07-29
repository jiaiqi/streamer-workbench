.PHONY: test test-golden test-unit run-backend run-ui requirements

# ── 金标准测试（全量像素对比） ──
test-golden:
	@echo "=== 金标准测试：全主题 × 2页 逐像素对比 ==="
	PYTHONPATH=. python tests/test_golden.py

# ── 单元测试（theme loader / Song 模型 / 布局） ──
test-unit:
	@echo "=== 单元测试 ==="
	PYTHONPATH=. python -m pytest tests/test_unit.py -v 2>&1 || PYTHONPATH=. python tests/test_unit.py

# ── 全部测试 ──
test: test-unit test-golden

# ── 后端 ──
run-backend:
	python -m server --reload --port 8000

# ── 前端 ──
run-ui:
	cd ui && npm run dev

# ── 安装 ──
requirements:
	pip install -r requirements.txt

# ── 导出当前默认组合 ──
export-sample:
	@echo "=== 导出海洋柔光全屏绕排 ×2页 ==="
	PYTHONPATH=. python -c "
from core.spec import get_canvas_spec
from core.themes.loader import load_themes
from core.layouts import get_layout
from core.data.songs import build_default_library
from core.engine import render_page
t = load_themes('themes')['海洋柔光']
l = get_layout('grid-wrap')
b = build_default_library()
s = get_canvas_spec('抖音全屏 9:20', avoid=True)
for p in (1,2):
    render_page(t, l, b, s, p, 'fonts/MaokenAssortedSans.ttf').save(f'output/sample-p{p}.png')
print('导出了 output/sample-p1.png output/sample-p2.png')
"

# ── 重新生成金标准参照图（从设计仓库复制） ──
regenerate-golden:
	PYTHONPATH=. python tools/regenerate_golden.py
