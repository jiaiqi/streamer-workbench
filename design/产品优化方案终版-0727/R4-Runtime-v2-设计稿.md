# R4 Runtime v2 — Layout Runtime 抽象设计稿

> **状态**：🟡 草案 v1（2026-08-12）
> **基准**：master `cb427b8`（M3 P3 ExportLogDrawer 收口）
> **前置**：R4 Runtime v1（`core/layouts/channel.py` + 30 项测试 + 4 套金标准 35/35）已交付
> **执行**：本文为设计稿；落地拆 3 批次收口（见 §8）

---

## 1. 概览

### 1.1 背景

R4 Runtime v1 在 2026-08-02 完成最小化抽象：只引入 `DataChannel` Literal 枚举 + `LayoutPlugin.supported_channels` 类属性声明 + `get_layout(channel=...)` 校验。**v1 不动渲染逻辑、不动接口签名，零金标准风险**。

但 v1 留下了 5 个真实差距（详见 §2）：

1. `analyze()` / `categorize()` 在 4 套 layout 签名不一致
2. 没有 `LayoutPlan` 数据结构
3. `Palette` / `Skin` 模型在 `core/themes/palette.py` + `core/themes/skin.py` 早定义了，但**完全没接进渲染管线**
4. `RenderDocument.parameters` 字段填充了，但 `engine.render_page()` 调 `DrawContext()` 时**没传**
5. `engine.render_pages()` 写死 `from .layouts.magazine_flow import analyze as _mf_analyze`

### 1.2 目标

在不破坏 R0-R3 既有金标准（16/16 grid-wrap + 4 套 PNG）的前提下，**真正把 v1 留下的 5 个差距补完**，并把 R4 抽象扩展为"稳定可演进"的契约层。

### 1.3 范围（v2 全部做）

| Spike | 内容 | 工作量 |
|---|---|---|
| V2.1 | `LayoutPlan / LayoutAnalysis / PagePlan / SectionPlan` dataclass + `LayoutPlugin.plan(library, ctx) -> LayoutPlan` 抽象方法 | 2h |
| V2.2 | 4 套 layout 统一 `analyze(library, ctx) -> LayoutAnalysis` 签名 + `engine.render_pages` 解耦 magazine_flow 写死 | 1.5h |
| V2.3 | `Palette` / `Skin` 真实接线（`engine.render_page` 接受 `palette/skin` 可选参；`ctx.palette` 双轨字段；`Skin.from_palette_and_layout` 工厂） | 2h |
| V2.4 | `parameters` 真正流到 `DrawContext`（单行修复 + 链路验证） | 0.5h |
| V2.5 | `LayoutPlugin.compatible_themes` + `Theme.compatible_layouts` 能力矩阵 + LayoutPicker 灰显 | 1.5h |
| **合计** | | **~7-8h** |

### 1.4 明确不做（推到 v3+）

- 路径排文（Path 弧形排版）
- 主体绕排 orbit / scatter
- 手动增删页 UI（`pages: list[PagePlan]` 数据结构先预留，UI 推迟）
- 页级覆盖（page-level overrides 字典先预留，UI 推迟）
- 编辑器（R7）— 与 R4 v2 无关
- 跨主题共用 layout 的"自动选最佳 theme"（v3 由数据反哺推动）

### 1.5 关键设计原则

1. **不破坏旧路径** — 16/16 金标准 0 像素差异
2. **双轨过渡** — 新字段加，旧字段保留；`ctx.style` 留作 fallback，`ctx.palette` 新增
3. **小步快跑** — 每改一个 layout 立即跑金标准 + 全部测试
4. **契约优先** — 数据结构（Plan）优先于实现细节
5. **零新依赖** — 全 stdlib + 已有项目依赖

---

## 2. 现状盘点

### 2.1 v1 已交付（保持稳定）

- `core/layouts/channel.py` — `DataChannel` Literal + `CHANNELS` 元组 + `normalize_channel / is_supported` 防御性 helper
- `LayoutPlugin.supported_channels: ClassVar[tuple[DataChannel, ...]] = ()` 字段
- `get_layout(id, channel=...)` / `list_layouts(channel=...)` 可选 channel 参数
- 4 套 layout 显式声明：`grid-wrap → song_library` / `magazine-flow → song_library` / `live-set → live_session` / `learning-report → learning_report`
- `live.py` / `learning_report.py` router 用 `get_layout(..., channel=...)` 显式校验
- 30 项 `tests/test_runtime_v1.py` + 4 套金标准 31/31 复跑通过

### 2.2 5 个真实差距

#### 差距 1：接口签名不一致

| Layout | `analyze()` | `categorize()` | `capabilities()` |
|---|---|---|---|
| `grid-wrap` | ❌ 没有 | `categorize(library)` | 走 base 默认 |
| `magazine-flow` | `analyze(library, canvas, axis=AXIS_NONE)` | `categorize(library, axis=AXIS_NONE, *, parameters=None)` | 重写 9 字段 |
| `live-set` | `analyze(library, canvas, **kwargs)` | `categorize(library)` | 重写 11 字段 |
| `learning-report` | `analyze(library, canvas, **kwargs)` | `categorize(library)` | 重写 10 字段 |

**问题**：
- grid-wrap 没有 analyze → 自动分页逻辑没法套
- 3 套 analyze 签名不一 → `engine.render_pages` 写死 magazine_flow
- 3 套 capabilities 字段顺序 / 类型不统一 → UI 难统一渲染

#### 差距 2：没有 LayoutPlan 数据结构

现状 layout 输出：
- `categorize(library) -> list[PageSections]` — 只有"sections"
- `render_page(ctx, page, library) -> int` — 直接画到 PIL，无中间结构

**缺**：
- "哪首歌在哪个栏目" 的可序列化结构（`SectionPlan.song_ids`）
- "哪首歌用了哪个字号" 的可追溯结构
- "页面整体布局的元数据"（页头/页脚/装饰带）

影响：
- 没法做"先 plan 后 render"的二级渲染（如先 grid 排，后画装饰）
- 没法做"导入旧 plan 再渲染"
- 没法做"页级覆盖"（v3 需要）

#### 差距 3：Palette/Skin 未接线

```bash
$ grep -rn "from .*Palette\|from .*Skin" core/ server/ --include="*.py" | grep -v core/themes/
# (no output)  ← 完全没有 import
```

`core/themes/palette.py` 定义了 `Palette` dataclass（含 5 颜色角色 + 4 字体角色 + name + source）
`core/themes/skin.py` 定义了 `Skin` dataclass（含 backgrounds / bg_strategy / subjects / mist_bottom_*/ param_overrides / extra_colors / compatibility / source）

**但 `engine.py` 走的是**：
```python
st: Style = theme.styles[page]   # 走 Style，不走 Palette
ctx = DrawContext(draw=d, spec=spec, style=st, ...)
```

Palette/Skin 是"领域模型骨架"但"未完整接入渲染"（产品优化方案终版.md 早期就这样说了）。

#### 差距 4：Parameters 哑字段

```python
# server/services/render_document.py:137
parameters=freeze(parameters or {}),   # ✅ 填充了

# server/services/render_document.py:145
return render_page(document.theme.materialize(), get_layout(document.layout_id),
                   library, document.canvas, document.page, document.font_path)
#       ^^^^^^^^^^ 上面没传 parameters
```

```python
# core/engine.py:88-101
def render_page(theme, layout, library, spec, page, font_path, skip_text=False):
    ...
    ctx = DrawContext(draw=d, spec=spec, style=st,
                      font_song=font, font_label=font_label)
    #         ^^^ 上面没传 parameters
```

```python
# core/context.py:39
parameters: Optional[dict] = None   # 字段定义了，但 engine 没传
```

`magazine-flow` 走 fallback 用 `getattr(ctx, "parameters", {})` 拿（兜底是 None）— 这就是 v1 阶段的妥协。

#### 差距 5：render_pages 写死

```python
# core/engine.py:128-133
def render_pages(...):
    fixed = layout.pages
    if page_count is None:
        if fixed:
            page_count = fixed
        else:
            # 兜底：自动分页由 layout.analyze 决定；若 layout 没实现则用 1
            from .layouts.magazine_flow import analyze as _mf_analyze   # ← 写死！
            try:
                page_count = _mf_analyze(library, axis="none", canvas=spec)["page_count"]
            except Exception:
                page_count = 1
```

`engine` 直接 import 具体 layout 模块，破坏抽象边界。

### 2.3 capabilities 字段对比（待统一）

| 字段 | grid-wrap | magazine-flow | live-set | learning-report |
|---|---|---|---|---|
| `supported_canvas_ids` | `["9:16", "9:20"]` | 5 个 | 4 个 | 4 个 |
| `required_theme_capabilities` | `[]` | `[]` | `[]` | `[]` |
| `supports_auto_pagination` | False | True | False | False |
| `supports_manual_pages` | False | True | False | False |
| `supports_grouping` | `["none", "chars"]` | 7 个 axis | `[]` | `[]` |
| `page_policy_mode` | `"legacy-fixed-2"` | `"auto"` | `"fixed-1"` | `"fixed-1"` |
| `max_density` | `{}` | `{"per_page": 36}` | 2 字段 | 3 字段 |
| `input_kind` | ❌ | ❌ | `"live_session_snapshot"` | `"learning_report_snapshot"` |
| `supported_channels` | ✅ | ✅ | ✅ | ✅ |

`input_kind` 字段**只在 2 套出现**，v2 应该统一从 `supported_channels` 派生（去掉 input_kind 字段）。

---

## 3. 抽象设计

### 3.1 LayoutPlan 数据结构（核心新增）

新文件：`core/layouts/plan.py`

```python
"""R4 Runtime v2: LayoutPlan 数据结构 — Layout 输入与输出中间层。

设计要点：
- 不可变 dataclass（frozen=True），可序列化、可哈希、可缓存
- 与 RenderDocument 类似：先生成 Plan，再用 Plan 渲染
- 不引入新依赖；纯 dataclass + types
- Plan 是「layout 自报的输出意图」，engine 据此选择「画法」；
  实际像素仍由 layout.render_page() 决定（保留向后兼容）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional, Tuple

# PageSection 排版策略（v2 锁定的 3 种；v3 增 Path/Orbit）
SectionLayoutKind = Literal["flow", "columns", "list"]


@dataclass(frozen=True)
class SectionPlan:
    """一页里的一个分类段。

    字段：
      label            分类标签（一字/二字/已唱/待唱/...)
      song_ids         该段包含的歌曲 ID 列表（与 library 一致）
      layout_kind      排版策略（v2: flow/columns/list）
      columns          栏数（1/2/3；0 = 跟随 page 级 columns）
      decoration       装饰带（v3 启用；v2 留 None）
      bbox             该段在画布上的预估 bbox (x1, y1, x2, y2)（可选；由 layout 估算）
    """
    label: str
    song_ids: Tuple[str, ...]
    layout_kind: SectionLayoutKind = "flow"
    columns: int = 1
    decoration: Optional[str] = None
    bbox: Optional[Tuple[float, float, float, float]] = None


@dataclass(frozen=True)
class PagePlan:
    """一页的完整计划。

    字段：
      page             页码（1-based）
      sections         该页的分类段列表
      header           页头（刊头/标题/期号；None = 无）
      footer           页脚（页码/装饰；None = 无）
      bg_strategy      背景策略（覆盖 Skin.bg_strategy；None = 走 Skin 默认）
    """
    page: int
    sections: Tuple[SectionPlan, ...]
    header: Optional[str] = None
    footer: Optional[str] = None
    bg_strategy: Optional[str] = None


@dataclass(frozen=True)
class LayoutAnalysis:
    """Layout 对输入数据的「预估分析」（不画图，只算元数据）。

    字段：
      page_count       预估页数（fixed 布局固定 2/1；auto 布局按内容算）
      overflow         是否超容量（grid-wrap 兼容用）
      degrade_reason   降级原因（"数据不足/超容量/无匹配" 等；None = 正常）
      sections_count   分类段总数
      axes_used        实际使用的分类轴（v2: chars/artist/genre/...）
      total_songs      输入歌曲数
      max_density      实际密度（与 capabilities.max_density 比对）
    """
    page_count: int
    overflow: bool = False
    degrade_reason: Optional[str] = None
    sections_count: int = 0
    axes_used: Tuple[str, ...] = ()
    total_songs: int = 0
    max_density: dict = field(default_factory=dict)


@dataclass(frozen=True)
class LayoutPlan:
    """Layout 对一次渲染输入的「完整输出计划」。

    字段：
      layout_id        "grid-wrap" / "magazine-flow" / ...
      layout_version   布局版本（v1 阶段固定 "1"；v2 起 layout 可自报）
      analysis         LayoutAnalysis
      pages            PagePlan 列表
      effective_palette_name  实际生效的 palette 名（v3 由 Skin 决定；v2 = theme.name）
      param_overrides  实际应用的参数覆盖（来自 Skin.param_overrides + 用户 parameters 合并）
    """
    layout_id: str
    layout_version: str = "1"
    analysis: LayoutAnalysis = field(default_factory=lambda: LayoutAnalysis(1))
    pages: Tuple[PagePlan, ...] = ()
    effective_palette_name: str = ""
    param_overrides: dict = field(default_factory=dict)
```

### 3.2 LayoutPlugin 抽象变化

`core/layouts/base.py` 在 v2 阶段变化最小（保持向后兼容）：

```python
class LayoutPlugin(ABC):
    # ... v1 字段全部保留 ...

    # ---- v2 新增：可选抽象（不破坏旧 layout）----
    def analyze(self, library, ctx: "LayoutContext") -> LayoutAnalysis:
        """v2: 统一签名 analyze(library, ctx)。

        - ctx.canvas: CanvasSpec
        - ctx.parameters: dict（来自 RenderDocument.parameters）
        - ctx.theme_capabilities: list[str]（主题能力名）

        v1 兼容：默认实现用 plugin.pages 构造最小 LayoutAnalysis。
        子类必须 override 才能让 analyze() 真正反映"auto 分页"等能力。
        """
        fixed = self.pages or 1
        return LayoutAnalysis(
            page_count=fixed,
            sections_count=0,  # 旧 layout 不预分析
        )

    def plan(self, library, ctx: "LayoutContext") -> LayoutPlan:
        """v2: 生成 LayoutPlan。

        默认实现：调 analyze() + categorize() + 简单组装。
        子类可 override 提供更精确的 PagePlan（如 magazine-flow 的双栏/三栏）。
        """
        analysis = self.analyze(library, ctx)
        sections = self.categorize(library, parameters=ctx.parameters)
        # 简单组装：把 PageSections 翻译成 PagePlan（v1 兼容路径）
        pages = tuple(
            PagePlan(
                page=ps.page,
                sections=tuple(
                    SectionPlan(label=sec["label"], song_ids=tuple(sec["songs"]))
                    for sec in ps.sections
                ),
            )
            for ps in sections
        )
        return LayoutPlan(
            layout_id=self.id,
            analysis=analysis,
            pages=pages,
        )

    # ---- v2 扩展：能力声明 ----
    def capabilities(self) -> dict:
        """v2: 统一 capabilities 字段。

        默认实现：返回 base 字段 + 派生 input_kind。
        input_kind 在 v2 阶段从 supported_channels 派生（去重）。
        """
        caps = {
            "supported_canvas_ids": ["9:16", "9:20"],
            "required_theme_capabilities": [],
            "supports_auto_pagination": False,
            "supports_manual_pages": False,
            "supports_grouping": ["none", "chars"],
            "page_policy_mode": "fixed-1" if not self.pages else f"fixed-{self.pages}",
            "max_density": {},
            "supported_channels": list(self.supported_channels),
        }
        # 派生 input_kind（v2 唯一一处 input_kind 出现）
        if self.supported_channels:
            caps["input_kind"] = f"{self.supported_channels[0]}_snapshot"
        return caps

    # ---- v2 扩展：能力矩阵 ----
    def compatible_themes(self) -> Tuple[str, ...]:
        """v2: 声明该 layout 适配哪些 theme。

        返回 theme id 元组（"海洋柔光" / "月夜星河" / ...）。
        默认空 tuple = 不限制（兼容所有 8 套）。
        子类可 override：例如 live-set 排除"梦幻海洋"（背景太花）。
        """
        return ()
```

### 3.3 DrawContext 扩展

`core/context.py` 在 v2 阶段变化最小（双轨过渡）：

```python
@dataclass
class DrawContext:
    draw: ImageDraw.ImageDraw
    spec: CanvasSpec
    style: Style                         # v1 字段保留
    font_song: ImageFont.FreeTypeFont
    font_label: ImageFont.FreeTypeFont
    # ---- v1 已定义但未激活 ----
    parameters: Optional[dict] = None
    # ---- v2 新增（双轨过渡）----
    palette: Optional["Palette"] = None  # 优先级 > style
    skin: Optional["Skin"] = None        # 优先级 > palette

    # ---- 排版公共能力（不变）----
    def r_at(self, y: int) -> int: ...
    @property
    def r_below(self) -> int: ...
    def draw_label(self, x, y, text): ...
    # ...

    # ---- v2 新增：Style 解析（双轨过渡核心）----
    @property
    def effective_style(self) -> Style:
        """v2: 优先级 skin > palette > style。

        - 无 skin/palette：返原 style（v1 行为，0 像素差异）
        - 有 palette：从 palette 重建 Style
        - 有 skin：先 palette 后 skin.apply_to(style)
        """
        if self.skin is not None and self.palette is not None:
            return self.skin.apply_to_style(self.style, self.palette)
        if self.palette is not None:
            return self.palette.to_style()
        return self.style
```

新文件：`core/layouts/ctx.py`（`LayoutContext` 给 plan/analyze 用，不依赖 PIL ImageDraw）：

```python
"""LayoutContext: 给 plan() / analyze() 用的非绘图上下文。"""
@dataclass(frozen=True)
class LayoutContext:
    canvas: CanvasSpec
    parameters: dict = field(default_factory=dict)
    theme_capabilities: Tuple[str, ...] = ()
    palette: Optional["Palette"] = None
    skin: Optional["Skin"] = None
```

### 3.4 Theme × Layout 能力矩阵

新结构（不引入新文件，在 Theme / LayoutPlugin 互相声明）：

```python
# core/themes/model.py 加字段
@dataclass
class Theme:
    # ... v1 字段保留 ...
    compatible_layouts: Tuple[str, ...] = ()   # v2 新增；空 = 全部兼容

# core/layouts/base.py 加方法
class LayoutPlugin(ABC):
    def compatible_themes(self) -> Tuple[str, ...]:
        return ()   # 空 = 全部兼容
```

`core/layouts/compat.py` 新文件（v2 收口时一并加）：

```python
def check_compatibility(layout_id: str, theme_id: str) -> tuple[bool, str]:
    """双向校验 layout × theme 兼容性。

    返回 (compatible, reason)：
    - True, ""：完全兼容
    - False, "reason"：不兼容 + 不兼容原因
    """
    layout = get_layout(layout_id)
    theme = load_theme_by_id(theme_id)
    # layout 自报不兼容的 theme
    if layout.compatible_themes() and theme_id not in layout.compatible_themes():
        return False, f"layout「{layout_id}」声明不兼容 theme「{theme_id}」"
    # theme 自报不兼容的 layout
    if theme.compatible_layouts and layout_id not in theme.compatible_layouts:
        return False, f"theme「{theme_id}」声明不兼容 layout「{layout_id}」"
    return True, ""
```

UI 端：`LayoutPicker` 在 `useEffect` 里并行调 `check_compatibility`，不兼容时按钮置灰 + tooltip。

---

## 4. 5 个 Spike 详设

### V2.1 · LayoutPlan 核心抽象

**改动**：
- 新增 `core/layouts/plan.py`（约 80 行）
  - `LayoutAnalysis` / `LayoutPlan` / `PagePlan` / `SectionPlan` / `SectionLayoutKind` 5 个 dataclass
  - 单元测试 `tests/test_plan_dataclasses.py`（约 25 项：frozen 不可变、序列化、哈希、字段必填）
- 新增 `core/layouts/ctx.py`（约 30 行）
  - `LayoutContext` dataclass（不可变）
- `core/layouts/__init__.py` 导出上述类

**不做**：
- 不动 4 套 layout 的实现
- 不动 engine.py
- 不动 DrawContext（下一 spike 才动）

**验证**：
- `pytest tests/test_plan_dataclasses.py` 25 项全过
- 16/16 金标准 0 像素差异
- 30 项 v1 测试 0 回归

**工作量**：2h

---

### V2.2 · 三段式契约统一

**改动**：
- `core/layouts/base.py`：
  - `analyze(library, ctx: LayoutContext) -> LayoutAnalysis` 抽象方法默认实现
  - 移除旧方法签名兼容路径（v1 analyze 是 optional override）
- 4 套 layout 全部重写 `analyze()`：
  - `grid_wrap.analyze()`：返回 `LayoutAnalysis(page_count=2, sections_count=7, axes_used=("chars",))`
  - `magazine_flow.analyze()`：保留现有逻辑，返回 `LayoutAnalysis(page_count=N, axes_used=(axis,))`
  - `live_set.analyze()`：固定 1 页，sections_count=4（已唱/待唱/完整清单/空队列）
  - `learning_report.analyze()`：固定 1 页，sections_count=4
- `core/engine.py` `render_pages`：
  - 删除 `from .layouts.magazine_flow import analyze as _mf_analyze`
  - 改用 `layout.analyze(library, LayoutContext(canvas=spec, parameters=kwargs.get("parameters", {})))["page_count"]`
- 4 套 layout 移除 `analyze(library, canvas, axis=...)` 旧签名的 wrapper（如有）

**不做**：
- 不动 render_page 渲染逻辑
- 不改 capabilities() 字段名（V2.5 才改 input_kind）

**验证**：
- `pytest tests/test_runtime_v2.py` 20 项新增（4 套 × 5 场景：analyze 返回 LayoutAnalysis / page_count 正确 / 签名统一 / 异常路径 / 边界）
- 16/16 + 4 套金标准 35/35 0 像素差异
- v1 30 项测试 0 回归
- v2.1 plan dataclass 测试 0 回归

**工作量**：1.5h

---

### V2.3 · Palette/Skin 真实接线（最大风险点）

**改动**：
- `core/themes/palette.py`：
  - 新增 `Palette.to_style() -> Style` 方法（用 5 颜色角色 + 默认字体构造 Style）
  - 已有 `to_style_dict()` 保留做 v1 兼容
- `core/themes/skin.py`：
  - 新增 `Skin.apply_to_style(base: Style, palette: Palette) -> Style` 方法
  - 工厂方法 `Skin.from_palette_and_layout(palette, layout_id, theme_name)` 补完
- `core/context.py` DrawContext 加 `palette: Optional[Palette] = None` + `skin: Optional[Skin] = None` 字段
  - `effective_style` property（优先级 skin > palette > style）
- `core/engine.py` `render_page()` 加可选参数 `palette: Palette = None` + `skin: Skin = None`
  - 传入后塞进 DrawContext
  - 渲染时用 `ctx.effective_style` 替代 `ctx.style`（v1 行为 0 差异）
- `server/services/render_document.py` `render_document()` 调 `engine.render_page(..., palette=..., skin=...)`（v2 阶段允许 None）
- `core/themes/skin_loader.py` 新文件（~50 行）：
  - `load_skin(skin_dir, theme, layout_id) -> Skin`（兼容 skin.json 暂未启用；先用 from_palette_and_layout 工厂）

**风险与缓解**：
- ⚠️ **ctx.style 用 effective_style 替代** — 任何 layout 用 `ctx.style` 取色都可能走错路径
  - 缓解：v2 阶段保留 `style` 字段，`effective_style` 只在 v2.3 显式传入 palette/skin 时被使用
  - **测试：所有 layout 都不传 palette/skin 跑金标准，0 差异**
- ⚠️ `Palette.to_style()` 默认字体可能与 theme.json 的 font 字段不一致
  - 缓解：v2.3 阶段 `Palette.to_style()` 用 ctx.style 已有字段填充字体，不引入新字体
- ⚠️ Skin.apply_to_style 覆盖逻辑要"叠加"而非"替换"
  - 缓解：先调 palette.to_style() 拿基础，再 apply skin 覆盖（如 Skin.param_overrides 合并到 spec）

**验证**：
- `pytest tests/test_palette_skin.py` 25 项新增：
  - Palette.to_style 5 颜色角色映射正确
  - Skin.from_palette_and_layout 工厂：8 主题 × 5 layout = 40 组合（用 parametrize 跑）
  - Skin.apply_to_style 优先级：skin > palette > base style
  - DrawContext.effective_style 4 种组合（无 / 只有 palette / 只有 skin / 都有）
- 16/16 + 4 套金标准 0 像素差异（**关键回归门**）
- v1 30 项 + v2.1/V2.2 测试 0 回归
- 手动验证：1 套 theme + 1 套 layout 走 Skin 路径，渲染结果与原版对比

**工作量**：2h

---

### V2.4 · Parameters 注入链路修复

**改动**：
- `core/engine.py` `render_page()` 加参数 `parameters: dict | None = None`
  - 塞进 `DrawContext(parameters=parameters)`
- `core/engine.py` `render_pages()` 加参数 `parameters: dict | None = None`，透传给 `render_page`
- `server/services/render_document.py` `render_document()` 调 `engine.render_page(..., parameters=document.parameters)`
  - `document.parameters` 已经是 FrozenMapping（不可变），转 dict 传入
- 4 套 layout 不动 — 已有 `getattr(ctx, "parameters", {})` fallback 兜底
  - 修复后 fallback 永远返真值，fallback 路径删除
- 验证：删 `magazine_flow.py:289` 的 `getattr(ctx, "parameters", {})` fallback，改用 `ctx.parameters` 直读

**风险与缓解**：
- ⚠️ 旧 layout 直接 `ctx.parameters` 取值，假设是 dict；如果 RenderDocument 传 FrozenMapping 会 attribute error
  - 缓解：`engine.render_page` 内部 `parameters=dict(parameters or {})`，engine 层做冻结→可变转换
- ⚠️ `live_set.py:228` 已有 `getattr(ctx, "parameters", {})` 兜底；说明 v1 阶段这个字段从来不为空
  - 验证：跑金标准确认不为空（其实一直就是 None，从未被激活）

**验证**：
- `pytest tests/test_parameters_injection.py` 12 项新增：
  - engine.render_page 接受 parameters=None 不报错
  - engine.render_page 接受 parameters={} 传给 ctx
  - engine.render_page 接受 parameters={"columns": 3} 传到 magazine-flow 实际改变排版
  - FrozenMapping 透传：render_document → engine → ctx 链路
  - 4 套 layout 各自读 ctx.parameters 拿到真值
- 16/16 + 4 套金标准 0 像素差异（不传 parameters = v1 行为）
- v1/v2.1/V2.2/V2.3 测试 0 回归

**工作量**：0.5h

---

### V2.5 · 能力矩阵 + UI 灰显

**改动**：
- `core/themes/model.py`：`Theme` dataclass 加 `compatible_layouts: Tuple[str, ...] = ()` 字段
  - 8 套 theme.json 暂不加（默认空 = 全兼容）
  - v2.5 收口时给 1 套 theme 演示：例如 `月夜星河.theme.json` 加 `"compatible_layouts": ["magazine-flow", "fullscreen-flow"]`（深色背景 grid-wrap 跳行）
- `core/layouts/base.py`：`LayoutPlugin` 加 `compatible_themes()` 方法（默认返空 tuple）
  - v2.5 收口时给 live-set 演示：`compatible_themes = ("梦幻海洋", "月夜星河", ...)` 排除"卡通音符"等
- `core/layouts/compat.py` 新文件（~50 行）：
  - `check_compatibility(layout_id, theme_id) -> tuple[bool, str]`
  - `list_compatible_layouts(theme_id) -> list[str]`（前端 UI 用）
  - `list_compatible_themes(layout_id) -> list[str]`
- `server/routers/posters.py`：新增 `GET /api/posters/compatibility?layout_id=&theme_id=` 端点
  - 返回 `{ compatible: bool, reason: str }`
  - 加 `GET /api/posters/compatibility/matrix` 端点：返回所有 layout × theme 组合的兼容矩阵（UI 启动时拉一次缓存）
- UI `ui/src/api/posters.ts`：加 `getCompatibilityMatrix()` 客户端
- UI `ui/src/posters/LayoutPicker.tsx`：
  - 启动时拉 matrix
  - 不兼容的 theme 在主题下拉里灰显 + tooltip
  - 切换 layout/poster 时实时校验，不兼容显示警告 banner
- `tests/test_compatibility_api.py` 10 项 Python 新增

**不做**：
- 不做"自动选最佳 theme"（v3 由数据反哺推动）
- 不做"主题自动适配"（v3 推动）

**风险与缓解**：
- ⚠️ v2.5 加 theme.json 字段可能让老 theme loader 失败
  - 缓解：theme loader 用 `.get("compatible_layouts", ())` 容忍缺失
  - 验证：8 套老 theme.json 全部加载成功
- ⚠️ UI 加新端点可能让 LayoutPicker 首屏慢
  - 缓解：matrix 端点带缓存（`@lru_cache` or FastAPI Depends 缓存），10 分钟过期

**验证**：
- `pytest tests/test_compatibility_api.py` 10 项新增：
  - check_compatibility 双向校验
  - 8 theme × 5 layout = 40 组合矩阵
  - 422 端点校验
- vitest `LayoutPicker.compatibility.test.tsx` 8 项新增：
  - 不兼容 theme 灰显
  - 切换 layout 触发警告
  - matrix 缓存生效
- 16/16 + 4 套金标准 0 像素差异
- 所有 v1/v2 测试 0 回归

**工作量**：1.5h

---

## 5. 风险评估与缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| V2.3 Palette/Skin 破坏 v1 路径 | 🔴 高 | 双轨过渡：保留 ctx.style 字段；effective_style 只在传入 palette/skin 时生效；16/16 金标准全程验证 |
| V2.2 改 analyze 签名连锁影响 | 🟡 中 | 小步快跑，每改 1 套 layout 立即跑金标准；用 LayoutContext 替换旧 canvas 参数 |
| V2.5 theme.json 字段破坏老 loader | 🟡 中 | `.get("compatible_layouts", ())` 容忍缺失；老 theme.json 全部加载成功验证 |
| V2.4 parameters 链路漏接 | 🟢 低 | engine 层加测试覆盖 4 套 layout；RenderDocument → engine → ctx 三处都加单测 |
| V2.1 frozen dataclass hash 冲突 | 🟢 低 | LayoutAnalysis 不放 list（用 tuple 替代）；用 `frozen=True` + `field(default_factory=tuple)` |
| v2 改动让 engine.py 体积膨胀 | 🟢 低 | render_page 拆 3 个 helper：`_load_fonts / _compose_base / _build_ctx` |

**总验证门**：
- 16/16 grid-wrap 金标准 0 像素差异
- 4 套 PNG 金标准 0 像素差异（magazine-flow 5/5 + live-set 5/5 + learning-report 5/5 + fullscreen-flow 4/4 = 19/19）
- 30 项 v1 测试 0 回归
- 60+ v2 新测试全过
- 1000+ 既有 Python 测试 0 回归
- tsc --noEmit 0 错
- 0 新增第三方依赖

---

## 6. v2 退出条件

### 6.1 必达（v2 收口判据）

- [ ] `core/layouts/plan.py` 落地：`LayoutAnalysis / LayoutPlan / PagePlan / SectionPlan` 5 个 dataclass 全部交付
- [ ] 4 套 layout 全部实现 `analyze(library, ctx: LayoutContext) -> LayoutAnalysis` 统一签名
- [ ] 4 套 layout 全部实现 `plan(library, ctx) -> LayoutPlan`（默认实现可，magazine-flow 自定义）
- [ ] `engine.render_pages()` 移除写死的 `from .layouts.magazine_flow import analyze` import
- [ ] `engine.render_page()` 支持 `palette / skin / parameters` 可选参
- [ ] `DrawContext.effective_style` 优先级正确（skin > palette > style）
- [ ] `Palette.to_style()` + `Skin.apply_to_style()` + `Skin.from_palette_and_layout()` 工厂全部实现
- [ ] `RenderDocument.parameters` 真正流到 `DrawContext.parameters`
- [ ] `check_compatibility(layout_id, theme_id)` 双向校验实现
- [ ] 1 套 theme + 1 套 layout 演示完整 Skin 路径（手动验证截图）

### 6.2 数据通道

- [ ] 4 套 layout 显式声明 `supported_channels`（v1 已完成，v2 不退化）
- [ ] `input_kind` 字段从 `supported_channels` 派生（去重，v1 阶段重复出现 2 次）
- [ ] 30 项 v1 测试全过

### 6.3 质量门

- [ ] 16/16 grid-wrap 金标准 0 像素差异
- [ ] 19/19 PNG 金标准 0 像素差异（magazine 5/5 + live-set 5/5 + learning-report 5/5 + fullscreen 4/4）
- [ ] 60+ v2 新测试全过
- [ ] v1 30 + 既有 1000+ Python 测试 0 回归
- [ ] vitest 全过（既有 700+ + 8 新增 LayoutPicker.compatibility）
- [ ] tsc --noEmit 0 错
- [ ] 0 新增第三方依赖

### 6.4 文档

- [ ] `路线图.md` 同步 R4 Runtime v2 收口状态
- [ ] `AGENTS.md` 同步当前完成状态（R4 v2 ✅ 收口）
- [ ] `README.md` API 列表加 1 端点（`GET /api/posters/compatibility`）
- [ ] `核心规划.md`（如有）同步 v2 数据结构

---

## 7. 暂不做（v3+）

| 项 | 推迟原因 | 建议 v3 阶段 |
|---|---|---|
| 路径排文（弧形/斜线排版） | 没有真实场景需求；v2 不应做"假想布局" | v3 由 Path Layout 需求推动 |
| 主体绕排 orbit / scatter | 需要"主体识别 + 几何避让"完整方案 | v3 由 P4 R7 编辑器推动 |
| 手动增删页 UI | `pages: list[PagePlan]` 数据结构已预留，UI 推迟 | v3 由"用户自定义分页"需求推动 |
| 页级覆盖 UI | `PagePlan.bg_strategy` / `SectionPlan.decoration` 已预留 | v3 与"手动增删页"同步 |
| 自动选最佳 theme | 需要 layout 评分 + 用户偏好数据 | v3 由数据反哺推动 |
| 跨主题共用 layout 的"主题适配" | 与"自动选最佳 theme"共生 | v3 推动 |
| 编辑器（R7） | 与 R4 v2 无关 | R7 阶段 |
| 主体识别（halo / vinyl-rings → subject-orbit 统一已 v0） | 已统一 | — |

**v2 阶段原则**：只做"被 2 个以上真实场景共用"的能力；不预先设计"假想布局需要"的接口。

---

## 8. 落地路线图（3 批次收口）

### 批次 1：V2.1 + V2.2 — 核心抽象 + 三段式统一

**工作量**：3.5h
**收口判据**：
- `core/layouts/plan.py` + `core/layouts/ctx.py` 落地
- 4 套 layout `analyze()` 统一签名
- `engine.render_pages` 移除写死 import
- 20 项 v2 测试新增
- 16/16 + 19/19 金标准 0 像素差异

**风险**：🟡 中（V2.2 改签名要小步快跑）

**commit 序列**：
- `feat(R4 v2.1): LayoutPlan dataclass + LayoutContext`
- `feat(R4 v2.2): 三段式契约统一 + render_pages 解耦`
- `docs(R4 v2.1+v2.2): AGENTS/README/路线图 同步收口`

---

### 批次 2：V2.3 + V2.4 — Palette/Skin 接线 + Parameters 注入

**工作量**：2.5h
**收口判据**：
- `Palette.to_style()` + `Skin.apply_to_style()` + `Skin.from_palette_and_layout()` 全部实现
- `engine.render_page` 接受 `palette/skin/parameters`
- `RenderDocument.parameters` 真正流到 `DrawContext`
- 1 套 theme + 1 套 layout 演示 Skin 路径（手动验证）
- 37 项 v2 测试新增（25 Palette/Skin + 12 parameters）
- 16/16 + 19/19 金标准 0 像素差异（**关键回归门**）

**风险**：🔴 高（V2.3 接管 ctx.style 是 v2 最大风险点）

**commit 序列**：
- `feat(R4 v2.3): Palette/Skin 真实接线 - ctx.effective_style 双轨过渡`
- `feat(R4 v2.4): parameters 真正流到 DrawContext - 链路修复`
- `docs(R4 v2.3+v2.4): AGENTS/README/路线图 同步收口`

---

### 批次 3：V2.5 — 能力矩阵 + UI 灰显

**工作量**：1.5h
**收口判据**：
- `core/themes/model.py` 加 `compatible_layouts` 字段
- `core/layouts/compat.py` + 3 端点（`compatibility` / `compatibility/matrix` / ...）
- 1 套 theme.json 演示 `compatible_layouts` 字段
- 1 套 layout 演示 `compatible_themes()` 方法
- LayoutPicker UI 灰显
- 10 项 Python + 8 项 vitest 新增
- 16/16 + 19/19 金标准 0 像素差异

**风险**：🟡 中（theme.json 字段兼容性）

**commit 序列**：
- `feat(R4 v2.5): 能力矩阵 - Theme×Layout 双向兼容 + UI 灰显`
- `docs(R4 v2.5): AGENTS/README/路线图 同步收口`

---

### 合并收口

3 批次完成后，单一 `merge(R4 v2): Layout Runtime v2 抽象` 收口 commit。
- master 累计 v2 收口后：v1 30 + v2 90 项测试；金标准 35/35 全过；零新依赖。

---

## 9. 附录

### 附录 A · 现有 LayoutPlugin 接口表（v2 改造前）

| 方法 | 抽象 | grid-wrap | magazine-flow | live-set | learning-report | fullscreen-flow |
|---|---|---|---|---|---|---|
| `id` | str | "grid-wrap" | "magazine-flow" | "live-set" | "learning-report" | "fullscreen-flow" |
| `name` | str | "全行网格绕排版" | "杂志式自动分页" | "直播复盘海报" | "学歌报告海报" | "全屏柔光绕排版" |
| `pages` | int\|None | 2 | None | 1 | 1 | None |
| `supports_avoidance` | bool | True | True | True | True | True |
| `supported_channels` | tuple | ("song_library",) | ("song_library",) | ("live_session",) | ("learning_report",) | ("song_library",) |
| `params()` | abstract | ✅ 4 字段 | ✅ 14 字段 | ✅ 4 字段 | ✅ 2 字段 | ✅ 2 字段 |
| `categorize()` | abstract | ✅ | ✅ + axis | ✅ | ✅ | ✅ |
| `render_page()` | abstract | ✅ | ✅ | ✅ | ✅ | ✅ |
| `capabilities()` | optional | 走 base 默认 | 重写 9 字段 | 重写 11 字段 | 重写 10 字段 | 走 base 默认 |
| `analyze()` | **v2 新增** | ❌ v1 没有 | ✅ 旧签名 | ✅ 旧签名 | ✅ 旧签名 | ❌ v1 没有 |
| `plan()` | **v2 新增** | ❌ | ❌ | ❌ | ❌ | ❌ |
| `extra_colors()` | optional | `{}` | 走 base | 走 base | 走 base | 走 base |
| `estimate_capacity()` | optional | ✅ | ❌ | ❌ | ❌ | ❌ |
| `check_overflow()` | optional | ✅ | ❌ | ❌ | ❌ | ❌ |
| `compatible_themes()` | **v2 新增** | ❌ | ❌ | ❌ | ❌ | ❌ |

### 附录 B · capabilities 字段差异（v2 收口目标）

**v2 收口时统一为**：

```python
def capabilities(self) -> dict:
    return {
        "supported_canvas_ids": [...],           # 所有 layout 都给（base 默认 ["9:16", "9:20"]）
        "required_theme_capabilities": [...],    # 必填字段名（v2 默认 []）
        "supports_auto_pagination": bool,        # 5 套必填（base 默认 False）
        "supports_manual_pages": bool,           # 5 套必填
        "supports_grouping": list[str],          # base 默认 ["none", "chars"]；live_set/learning_report 改为 ["none"]
        "page_policy_mode": str,                 # 5 套必填；base 默认 "fixed-1" 或 f"fixed-{self.pages}"
        "max_density": dict,                     # base 默认 {}；各 layout 自报
        "supported_channels": list,              # v1 阶段统一从类属性派生
        "input_kind": str,                       # v2 阶段从 supported_channels[0] 派生（v1 阶段重复 2 次去重）
    }
```

**v2 阶段不加的字段**（v3 再说）：
- `preview_render_ms`：性能指标，不在 v2 范围
- `required_fonts`：字体需求，跟 palette 走更合理
- `decorations`：装饰带，跟 page-level 一起做

### 附录 C · LayoutPlan 序列化样例（v2 阶段示例）

```python
# magazine-flow 输入 36 首歌 + axis="chars" 的 LayoutPlan 输出
LayoutPlan(
    layout_id="magazine-flow",
    layout_version="1",
    analysis=LayoutAnalysis(
        page_count=3,
        sections_count=8,
        axes_used=("chars",),
        total_songs=36,
        max_density={"per_page": 12},
    ),
    pages=(
        PagePlan(
            page=1,
            sections=(
                SectionPlan(label="一字", song_ids=("枫", "耿"), columns=3),
                SectionPlan(label="二字", song_ids=("后来", "红豆"), columns=2),
                SectionPlan(label="三字", song_ids=("恋爱ing", "黑色毛衣"), columns=2),
            ),
            header="2026.08 一字二字三期",
        ),
        PagePlan(page=2, sections=(...)),
        PagePlan(page=3, sections=(...)),
    ),
    effective_palette_name="海洋柔光",
    param_overrides={"columns": 2, "columns_per_section": {...}},
)
```

可序列化（`asdict(plan)` 直接转 dict）→ 可缓存（hash by `(layout_id, page_count, song_count, axes_used)`）→ 可复用（"先生成 plan 再画" 二级渲染）。

### 附录 D · 与 R4 退出条件对接

R4 退出条件在 `路线图.md`：

```text
- [ ] 三个场景使用同一稳定计划格式（LayoutPlan）    ← V2.1 满足
- [ ] magazine 与 grid-wrap 构图本质不同            ← 既有，不退化
- [ ] 新旧布局可在同一工作台选择                     ← R4.0 P2 ✅
- [ ] 公共能力至少被两个场景复用                     ← V2.1 + V2.3 满足
- [ ] 不存在只为假想布局服务的必选接口                ← v2 范围守住
- [ ] draft/full 语义结果一致                        ← 既有，不退化
- [ ] grid-wrap 仍固定两页且 16/16                   ← 16/16 守住
- [x] DataChannel 协议（v1 完成）
- [ ] 专用海报区产生日活（live-set / learning-report）← 部署后观察
- [ ] EmptyState/Spinner/StatusBadge/ErrorBanner 统一 ← R4.1 ✅
- [ ] R3.6 退出门 5/5 维度已接                       ← R4.2 ✅
```

**v2 收口 = R4 退出条件 4/11 全部满足**：
- ✅ LayoutPlan 稳定计划格式
- ✅ Palette/Skin 真实接线（2 场景共用能力）
- ✅ grid-wrap 16/16 守住
- ✅ 公共能力被 2 场景复用

**v2 收口 = R4 进度 50% → 80%**。

---

## 10. 修订记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-08-12 | v1 草案 | 初稿：现状盘点 + 抽象设计 + 5 spike 详设 + 3 批次收口路线图 |
