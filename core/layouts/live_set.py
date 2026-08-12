"""live-set 布局（R2.5）—— 直播复盘海报。

设计要点（路线图 R2.5）：
- 输入：LiveSession 完整快照（不是 SongLibrary）
  → 包含 session 元数据 + 全部 SongRequest + 全部 PerformanceRecord
  → 绕过 grid-wrap / magazine-flow 那条「已会曲库 → 海报」的路径
  → 因为「直播复盘」是事件驱动，不是曲库快照
- 单页布局（pages=1）：所有内容塞一张海报
- 数据通道：
  - library（duck-typed）：LiveSessionSnapshot
  - ctx.parameters：可选 metadata（session_title / session_started_at / 等）
- 空场降级：完全空数据 → 标题区 + 「空场直播」+ 统计 0/0/0
- 6 个 ParamSpec：边距、当前/已唱字号、待唱字号、显示时间戳、显示点歌人

排版结构（自顶向下 9:20 / 9:16 都适配）：
  ① 标题区 [120px]   直播标题 + 状态徽章
  ② 副标题 [40px]    日期 + 规则版本 + 主持
  ③ 统计 [70px]      全部/已唱/待唱/跳过 pill 三联
  ④ 当前演唱 [120px] 高亮 current 歌曲（大字号 + 点歌人 + 入场时间）
  ⑤ 待唱列表 [动态]  N 行：编号 + 歌名（小字号） + 点歌人
  ⑥ 已唱列表 [动态]  M 行：歌名 + 演唱时间 + ✓/✗/⏸ 标记
  ⑦ 完整清单 [动态]  所有歌曲按时间顺序
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Mapping, Optional

from .base import LayoutPlugin, PageSections, ParamSpec
from ..context import DrawContext
from .ctx import LayoutContext
from .plan import LayoutAnalysis
from . import _common


# ── LiveSessionSnapshot：live-set 专用数据通道 ──
#
# 不与 SongLibrary 共享：live-set 的输入是「一场直播的事件流」，
# 不是「主播会唱的所有歌」。两套数据通道并存，由 layout 插件 id 区分。
#
# 字段：
#   session_id: str             直播场次 ID
#   session_title: str          直播标题
#   session_state: str          "active" / "closed"
#   started_at: str             ISO 时间
#   closed_at: Optional[str]    关闭时间
#   rule_version: str           点歌规则版本
#   requests: list[dict]        所有 SongRequest 序列化
#                                {id, song_id, song_title, requester_name,
#                                 requested_at, entitlement_kind, is_bumped}
#   performances: list[dict]    所有 PerformanceRecord 序列化（按 request_id 索引）
#                                {request_id, song_id, song_title, result,
#                                 performed_at, reason}


@dataclass(frozen=True)
class LiveSessionSnapshot:
    """live-set 海报的输入数据（不可变快照）。"""

    session_id: str = ""
    session_title: str = ""
    session_state: str = "active"
    started_at: str = ""
    closed_at: Optional[str] = None
    rule_version: str = ""
    requests: tuple = ()
    performances: tuple = ()

    @property
    def total_count(self) -> int:
        return len(self.requests)

    @property
    def sung_count(self) -> int:
        return sum(1 for p in self.performances
                   if p.get("result") == "sung")

    @property
    def queued_count(self) -> int:
        """待唱：请求中尚未演唱的（无对应 sung 演唱记录），且不在 current 状态。"""
        sung_request_ids = {p.get("request_id") for p in self.performances
                            if p.get("result") == "sung"}
        return sum(1 for r in self.requests
                   if r.get("id") not in sung_request_ids
                   and r.get("state") != "current")

    @property
    def current_count(self) -> int:
        """当前演唱中（state=current 的请求，对应 1 首）。"""
        return sum(1 for r in self.requests
                   if r.get("state") == "current")

    def categorize(self) -> dict[str, list[dict]]:
        """把请求/演唱按状态分桶，供 render_page 使用。"""
        sung_by_request = {p.get("request_id"): p
                           for p in self.performances
                           if p.get("result") == "sung"}
        current = [r for r in self.requests
                   if r.get("state") == "current"]
        # 待唱 = 没被 sung 也没被取消的
        cancelled_ids = {p.get("request_id") for p in self.performances
                         if p.get("result") in ("cancelled", "skipped", "postponed", "duplicate_merged")}
        queued = [r for r in self.requests
                  if r.get("id") not in sung_by_request
                  and r.get("id") not in cancelled_ids
                  and r.get("state") != "current"]
        # 已唱 = sung 表演记录，按 performed_at 倒序
        sung = [p for p in self.performances
                if p.get("result") == "sung"]
        sung.sort(key=lambda p: p.get("performed_at", ""), reverse=True)
        # 跳过/取消
        skipped = [p for p in self.performances
                   if p.get("result") in ("skipped", "cancelled", "postponed", "unknown")]
        return {
            "current": current,
            "queued": queued,
            "sung": sung,
            "skipped": skipped,
        }


# 状态字符、日期格式、歌名标签等公共 helper 全部从 ._common 导入（R4.0 抽出）；
# 旧 _format_date / _safe / _RESULT_GLYPH 模块级函数已在 R4.0 删除，调用点
# 保持原名以最小化 render_page 内 diff，行为完全等价。
from ._common import (  # noqa: E402  - 紧贴 LiveSetLayout 之前方便阅读
    format_date_long as _format_date,
    safe_label as _safe,
    RESULT_GLYPH as _RESULT_GLYPH,
    EMPTY_TITLE_FALLBACK as _EMPTY_TITLE,
)


class LiveSetLayout(LayoutPlugin):
    """R2.5: 直播复盘海报布局（单页）。"""

    id = "live-set"
    name = "直播复盘"
    pages = 1                 # 单页布局
    supports_avoidance = True
    # R4 Runtime v1: 走 LiveSessionSnapshot 数据通道
    supported_channels = ("live_session",)

    def params(self) -> list[ParamSpec]:
        return [
            ParamSpec("margin", "边距", "int", 58, min=0, max=200,
                      group="画布", unit="px", step=2,
                      help="四边留白，0 表示贴边"),
            ParamSpec("font_current", "当前演唱字号", "int", 56, min=30, max=80,
                      group="样式", unit="pt", step=1,
                      help="当前演唱中的歌曲字号"),
            ParamSpec("font_queued", "待唱歌号", "int", 32, min=20, max=56,
                      group="样式", unit="pt", step=1,
                      help="待唱列表歌曲字号"),
            ParamSpec("font_sung", "已唱歌号", "int", 30, min=20, max=56,
                      group="样式", unit="pt", step=1,
                      help="已唱列表歌曲字号"),
            ParamSpec("show_timestamps", "显示时间", "bool", True,
                      group="样式",
                      help="演唱时间 / 入场时间是否显示"),
            ParamSpec("show_requester", "显示点歌人", "bool", True,
                      group="样式",
                      help="待唱 / 已唱列表是否显示点歌人"),
        ]

    def capabilities(self) -> dict:
        """live-set 能力声明：只支持 9:20 / 9:16，不需要主题能力。"""
        return {
            "supported_canvas_ids": [
                "9:20", "9:16",
                "抖音全屏 9:20", "标准 9:16",
            ],
            "required_theme_capabilities": [],
            "supports_auto_pagination": False,
            "supports_manual_pages": False,
            "supports_grouping": [],            # 不用 axis 分类
            "page_policy_mode": "fixed-1",
            "max_density": {
                "queued_max": 30,
                "sung_max": 30,
            },
            # 标识这不是从 SongLibrary 派生的
            "input_kind": "live_session_snapshot",
            # R4 Runtime v1: 与 supported_channels 类属性保持一致
            "supported_channels": list(self.supported_channels),
        }

    def analyze(self, library: LiveSessionSnapshot, ctx: LayoutContext, **kwargs) -> LayoutAnalysis:
        """R4 Runtime v2: 统一签名 analyze(library, ctx)。

        live-set 固定 1 页；返回 4 个分类（当前演唱/待唱/已唱/跳过）的分析。

        v1 兼容：ctx 可为 LayoutContext / CanvasSpec / duck-typed
        canvas-like 对象（有 width/height/margin 字段）。
        """
        from .ctx import LayoutContext
        from ..spec import CanvasSpec
        if not isinstance(ctx, LayoutContext):
            if isinstance(ctx, CanvasSpec) or (
                hasattr(ctx, "width") and hasattr(ctx, "height")
            ):
                # 接受 CanvasSpec 或 duck-typed canvas；走 base 默认（live-set 不依赖 ctx 内容）
                pass
            else:
                raise TypeError(
                    f"ctx 期望 LayoutContext/CanvasSpec/canvas-like，得到 {type(ctx).__name__}"
                )
        if not isinstance(library, LiveSessionSnapshot):
            return LayoutAnalysis(
                page_count=1,
                degrade_reason="library 不是 LiveSessionSnapshot",
                sections_count=0,
            )
        buckets = library.categorize()
        return LayoutAnalysis(
            page_count=1,
            sections_count=4,
            total_songs=library.total_count,
            max_density={
                "sung_count": library.sung_count,
                "queued_count": library.queued_count,
                "current_count": library.current_count,
                "skipped_count": len(buckets.get("skipped", [])),
            },
        )

    def categorize(self, library) -> list[PageSections]:
        """live-set 永远单页；返回 1 个空 section（render_page 不用）。"""
        if not isinstance(library, LiveSessionSnapshot):
            return [PageSections(page=1, sections=[])]
        return [PageSections(page=1, sections=[])]

    def render_page(self, ctx: DrawContext, page: int, library) -> int:
        """渲染直播复盘海报。

        协议：
        - library 必须是 LiveSessionSnapshot
        - page 必须 = 1
        - 任何错误输入（None / 错类型）→ 渲染空场降级
        """
        if page != 1:
            return 0
        if not isinstance(library, LiveSessionSnapshot):
            library = LiveSessionSnapshot()
        params = ctx.parameters or {}  # R4 Runtime v2: ctx.parameters 始终有值（V2.4 链路修复）
        if not isinstance(params, Mapping):
            params = {}
        margin = int(params.get("margin", 58) or 58)
        f_current = int(params.get("font_current", 56) or 56)
        f_queued = int(params.get("font_queued", 32) or 32)
        f_sung = int(params.get("font_sung", 30) or 30)
        show_ts = bool(params.get("show_timestamps", True))
        show_req = bool(params.get("show_requester", True))

        spec = ctx.spec
        d = ctx.draw
        st = ctx.style
        OFF = spec.content_offset
        W = spec.width
        M = margin
        buckets = library.categorize()

        # ── ① 标题区 ──
        y = 80 + OFF
        title_text = (library.session_title or "直播复盘").strip()
        try:
            font_title = ctx.font_title
        except AttributeError:
            font_title = ctx.font_song
        # 标题（按宽度截断，避免溢出）
        title_max_w = W - 2 * M
        if d.textlength(title_text, font=font_title) > title_max_w:
            while len(title_text) > 4 and d.textlength(title_text + "…", font=font_title) > title_max_w:
                title_text = title_text[:-1]
            title_text = title_text + "…"
        d.text((M, y), title_text, font=font_title, fill=st.text)
        # 状态徽章（右上角 pill）
        badge_text = "● 进行中" if library.session_state == "active" else "■ 已结束"
        is_active = library.session_state == "active"
        badge_w = d.textlength(badge_text, font=ctx.font_label) + 36
        badge_x = W - M - badge_w
        badge_y = y - 6
        _common.draw_pill(
            d, badge_x, badge_y, badge_text, ctx.font_label,
            st.pill if is_active else st.mist,
            st.label if is_active else st.text,
        )
        y += 70

        # ── ② 副标题：日期 + 规则版本 ──
        subtitle_parts = []
        if library.started_at:
            subtitle_parts.append(_format_date(library.started_at))
        if library.rule_version:
            rv = library.rule_version
            if rv.startswith("rule_"):
                rv = rv[5:13]  # 取前 8 字符
            subtitle_parts.append(f"规则 {rv}")
        if library.closed_at and library.session_state == "closed":
            subtitle_parts.append(f"结束 {_format_date(library.closed_at)}")
        if subtitle_parts:
            d.text((M, y), " · ".join(subtitle_parts), font=ctx.font_song, fill=st.mist)
            y += 50

        # ── ③ 统计 pill 三联 ──
        total = library.total_count
        sung = library.sung_count
        queued = library.queued_count
        current = library.current_count
        stats = [
            (f"共 {total} 首", st.pill, st.label),
            (f"已唱 {sung}", st.pill, st.label),
            (f"待唱 {queued}", st.mist, st.text),
        ]
        if current > 0:
            stats.append((f"演唱中 {current}", st.pill, st.label))
        stat_x = M
        for txt, bg, fg in stats:
            tw = _common.draw_pill(d, stat_x, y, txt, ctx.font_label, bg, fg)
            stat_x += tw + 12
        y += 60

        # 分隔线
        _common.horizontal_rule(d, M, W - M, y, st.line)
        y += 16

        # ── 空场降级 ──
        if total == 0 and current == 0:
            y_big = spec.height // 2 - 80
            empty_msg = "空场直播"
            d.text((M, y_big), empty_msg, font=font_title, fill=st.mist)
            d.text((M, y_big + 80), "（本场暂无点歌记录）", font=ctx.font_song, fill=st.mist)
            return y_big + 160

        # ── ④ 当前演唱区 ──
        if buckets["current"]:
            cur = buckets["current"][0]
            y = self._draw_section_label(ctx, M, y, "● 当前演唱")
            # 大字号歌名
            song_title = (cur.get("song_title") or "（无题）").strip()
            if d.textlength(song_title, font=ctx.font_label) > (W - 2 * M):
                # 字号超出则降一档
                font_use = ctx.font_song
            else:
                font_use = ctx.font_label
            d.text((M, y), song_title, font=font_use, fill=st.text)
            y += f_current + 8
            # 点歌人 + 入场时间
            meta_parts = []
            if show_req and cur.get("requester_name"):
                meta_parts.append(f"点歌：{cur['requester_name']}")
            if show_ts and cur.get("requested_at"):
                meta_parts.append(f"入场 {_format_date(cur['requested_at'])}")
            if cur.get("is_bumped"):
                meta_parts.append("⚡ 插队")
            if meta_parts:
                d.text((M, y), " · ".join(meta_parts), font=ctx.font_song, fill=st.mist)
                y += 40
            y += 8

        # ── ⑤ 待唱列表 ──
        if buckets["queued"]:
            queued = buckets["queued"]
            y = self._draw_section_label(ctx, M, y, f"待唱 · {len(queued)} 首")
            for i, req in enumerate(queued[:30], start=1):
                text = _safe(req.get("song_title", ""), req.get("requester_name", ""))
                if not show_req:
                    text = (req.get("song_title") or "（无题）").strip()
                # 编号 + 歌名
                d.text((M, y), f"{i:02d}", font=ctx.font_song, fill=st.mist)
                tx = M + 50
                # 截断超宽
                if d.textlength(text, font=ctx.font_song) > (W - tx - M - 80):
                    while len(text) > 2 and d.textlength(text + "…", font=ctx.font_song) > (W - tx - M - 80):
                        text = text[:-1]
                    text = text + "…"
                d.text((tx, y), text, font=ctx.font_song, fill=st.text)
                # 入场时间（右侧）
                if show_ts and req.get("requested_at"):
                    ts = _format_date(req["requested_at"])
                    tsw = d.textlength(ts, font=ctx.font_song)
                    d.text((W - M - tsw, y), ts, font=ctx.font_song, fill=st.mist)
                y += f_queued + 6
                if y >= spec.height - margin - 100:
                    # 超出底部，提示「还有 N 首」
                    remain = len(queued) - i
                    if remain > 0:
                        d.text((M, y), f"…还有 {remain} 首未唱",
                               font=ctx.font_song, fill=st.mist)
                        y += 40
                    break
            y += 10

        # ── ⑥ 已唱列表 ──
        if buckets["sung"]:
            sung = buckets["sung"]
            y = self._draw_section_label(ctx, M, y, f"✓ 已唱 · {len(sung)} 首")
            for rec in sung[:30]:
                glyph = _RESULT_GLYPH.get(rec.get("result", ""), "·")
                song_title = (rec.get("song_title") or "（无题）").strip()
                if show_req and rec.get("requester_name"):
                    text = f"{song_title} · {rec['requester_name']}"
                else:
                    text = song_title
                # 截断
                max_w = W - 2 * M - 110
                if d.textlength(text, font=ctx.font_song) > max_w:
                    while len(text) > 2 and d.textlength(text + "…", font=ctx.font_song) > max_w:
                        text = text[:-1]
                    text = text + "…"
                d.text((M, y), glyph, font=ctx.font_song, fill=st.text)
                d.text((M + 24, y), text, font=ctx.font_song, fill=st.text)
                # 演唱时间
                if show_ts and rec.get("performed_at"):
                    ts = _format_date(rec["performed_at"])
                    tsw = d.textlength(ts, font=ctx.font_song)
                    d.text((W - M - tsw, y), ts, font=ctx.font_song, fill=st.mist)
                y += f_sung + 6
                if y >= spec.height - margin - 60:
                    remain = len(sung) - (sung.index(rec) + 1)
                    if remain > 0:
                        d.text((M, y), f"…还有 {remain} 首已唱",
                               font=ctx.font_song, fill=st.mist)
                        y += 40
                    break
            y += 10

        # ── ⑦ 跳过/取消列表（如果有） ──
        if buckets["skipped"]:
            y = self._draw_section_label(ctx, M, y,
                                         f"跳过/取消 · {len(buckets['skipped'])} 首")
            for rec in buckets["skipped"][:10]:
                glyph = _RESULT_GLYPH.get(rec.get("result", ""), "·")
                song_title = (rec.get("song_title") or "（无题）").strip()
                reason = rec.get("reason", "")
                text = f"{song_title}"
                if reason:
                    text = f"{text} ({reason})"
                d.text((M, y), glyph, font=ctx.font_song, fill=st.mist)
                d.text((M + 24, y), text, font=ctx.font_song, fill=st.mist)
                y += 32
                if y >= spec.height - margin:
                    break

        return y

    def _draw_section_label(self, ctx: DrawContext, x: int, y: int, text: str) -> int:
        """画分节标签，返回新 y。R4.0 起内部走 _common.draw_section_label。

        保留方法签名仅为 render_page 调用点不变，行为与原实现完全等价。
        """
        return _common.draw_section_label(ctx, x, y, text)
