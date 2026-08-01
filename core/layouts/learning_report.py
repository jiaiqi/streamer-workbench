"""learning-report 布局（R3.5）—— 学歌报告海报。

设计要点（路线图 R3.5）：
- 输入：LearningReportSnapshot（学歌事件聚合 + 曲库状态）
  → 不与 grid-wrap / magazine-flow 共享 SongLibrary 路径
  → 不与 live-set 共享 LiveSessionSnapshot 路径
  → 三套布局 = 三条独立数据通道
- 单页布局（pages=1）：所有内容塞一张海报
- 数据通道：
  - library（duck-typed）：LearningReportSnapshot
  - ctx.parameters：可选 metadata（report_title / period_label / 等）
- 空报告降级：标题区 + 「暂无学习数据」+ 提示语

排版结构（自顶向下 9:20 / 9:16 都适配）：
  ① 报告标题区 [120px]  "学习报告" + period 标签
  ② 副标题 [40px]     日期范围
  ③ 核心数据 pill [70px]  累计练习 / 次数 / 学会 / 连续打卡
  ④ 本月新学 [动态]    编号 + 歌名 + 学会时间
  ⑤ Top 歌手 [左栏]   + 调性分布 [右栏]
  ⑥ 完整时间线 [动态]  最近 N 次练习
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Mapping, Optional, Tuple

from .base import LayoutPlugin, PageSections, ParamSpec
from ..context import DrawContext


# ── LearningReportSnapshot：learning-report 专用数据通道 ──
#
# 不与 SongLibrary / LiveSessionSnapshot 共享：learning-report 的输入是
# 「一段时间窗口的练习/学会事件聚合 + 曲库当前统计」。
# 三套布局 = 三条独立数据通道，由 layout 插件 id 区分。
#
# 字段：
#   report_title: str            "学歌报告"（顶层标题）
#   period_label: str            "2026 年 6 月"（副标题 / 时间段）
#   period_start: str            ISO 时间
#   period_end: str              ISO 时间
#   total_practice_minutes: int
#   total_practice_sessions: int
#   current_streak_days: int
#   longest_streak_days: int
#   songs_learned: tuple         [{id, title, learned_at, artist}]
#   recent_practice: tuple       [{title, minutes, self_rating, occurred_at, note}]
#   top_artists: tuple           [{name, count}]
#   difficulty_buckets: tuple    [{label, count}]
#   key_buckets: tuple           [{label, count}]


@dataclass(frozen=True)
class LearningReportSnapshot:
    """learning-report 海报的输入数据（不可变快照）。"""

    report_title: str = "学歌报告"
    period_label: str = ""
    period_start: str = ""
    period_end: str = ""
    total_practice_minutes: int = 0
    total_practice_sessions: int = 0
    current_streak_days: int = 0
    longest_streak_days: int = 0
    songs_learned: tuple = ()
    recent_practice: tuple = ()
    top_artists: tuple = ()
    difficulty_buckets: tuple = ()
    key_buckets: tuple = ()

    @property
    def is_empty(self) -> bool:
        return (self.total_practice_sessions == 0
                and len(self.songs_learned) == 0
                and len(self.recent_practice) == 0)

    def analyze_summary(self) -> dict:
        """给后端 /analyze 端点用的桶摘要。"""
        return {
            "total_practice_minutes": self.total_practice_minutes,
            "total_practice_sessions": self.total_practice_sessions,
            "songs_learned_count": len(self.songs_learned),
            "recent_practice_count": len(self.recent_practice),
            "top_artists_count": len(self.top_artists),
            "difficulty_buckets_count": len(self.difficulty_buckets),
            "key_buckets_count": len(self.key_buckets),
            "current_streak_days": self.current_streak_days,
            "longest_streak_days": self.longest_streak_days,
        }


# ── 工具函数 ──

def _format_date(iso: str) -> str:
    """ISO 时间压成 'MM-DD'，失败原样返回。"""
    if not iso or "T" not in iso:
        return iso or ""
    date_part = iso[:10]
    return date_part[5:] if len(date_part) >= 10 else date_part


def _format_date_range(start: str, end: str) -> str:
    if start and end:
        return f"{_format_date(start)} → {_format_date(end)}"
    if start:
        return f"自 {_format_date(start)}"
    return ""


def _truncate(s: str, max_w: int, d, font) -> str:
    if d.textlength(s, font=font) <= max_w:
        return s
    while len(s) > 2 and d.textlength(s + "…", font=font) > max_w:
        s = s[:-1]
    return s + "…"


class LearningReportLayout(LayoutPlugin):
    """R3.5: 学歌报告海报布局（单页）。"""

    id = "learning-report"
    name = "学歌报告"
    pages = 1
    supports_avoidance = True

    def params(self) -> list[ParamSpec]:
        return [
            ParamSpec("margin", "边距", "int", 58, min=0, max=200,
                      group="画布", unit="px", step=2,
                      help="四边留白"),
            ParamSpec("font_title", "标题字号", "int", 60, min=30, max=80,
                      group="样式", unit="pt", step=1,
                      help="报告主标题字号"),
            ParamSpec("font_section", "章节字号", "int", 32, min=20, max=56,
                      group="样式", unit="pt", step=1,
                      help="章节标签 + 歌名 / 歌手字号"),
            ParamSpec("show_timeline", "显示时间线", "bool", True,
                      group="样式",
                      help="是否显示完整时间线（最近练习）"),
            ParamSpec("top_n_artists", "歌手 Top N", "int", 5, min=1, max=10,
                      group="样式", step=1,
                      help="Top 歌手显示数量"),
        ]

    def capabilities(self) -> dict:
        return {
            "supported_canvas_ids": [
                "9:20", "9:16",
                "抖音全屏 9:20", "标准 9:16",
            ],
            "required_theme_capabilities": [],
            "supports_auto_pagination": False,
            "supports_manual_pages": False,
            "supports_grouping": [],
            "page_policy_mode": "fixed-1",
            "max_density": {
                "songs_learned_max": 20,
                "timeline_max": 20,
                "artists_max": 10,
            },
            "input_kind": "learning_report_snapshot",
        }

    def analyze(self, library, canvas, **kwargs) -> dict:
        if not isinstance(library, LearningReportSnapshot):
            return {
                "page_count": 1,
                "empty": True,
                "degrade_reason": "library 不是 LearningReportSnapshot",
            }
        summary = library.analyze_summary()
        summary["page_count"] = 1
        summary["empty"] = library.is_empty
        return summary

    def categorize(self, library) -> list[PageSections]:
        if not isinstance(library, LearningReportSnapshot):
            return [PageSections(page=1, sections=[])]
        return [PageSections(page=1, sections=[])]

    def render_page(self, ctx: DrawContext, page: int, library) -> int:
        if page != 1:
            return 0
        if not isinstance(library, LearningReportSnapshot):
            library = LearningReportSnapshot()
        params = getattr(ctx, "parameters", {}) or {}
        if not isinstance(params, Mapping):
            params = {}
        margin = int(params.get("margin", 58) or 58)
        f_title = int(params.get("font_title", 60) or 60)
        f_section = int(params.get("font_section", 32) or 32)
        show_timeline = bool(params.get("show_timeline", True))
        top_n_artists = int(params.get("top_n_artists", 5) or 5)

        spec = ctx.spec
        d = ctx.draw
        st = ctx.style
        OFF = spec.content_offset
        W = spec.width
        M = margin

        # ── ① 报告标题区 ──
        y = 100 + OFF
        try:
            font_title_big = ctx.font_title
        except AttributeError:
            font_title_big = ctx.font_song
        # 主标题
        report_title = (library.report_title or "学歌报告").strip()
        d.text((M, y), report_title, font=font_title_big, fill=st.text)
        y += f_title + 4
        # 副标题：period_label
        if library.period_label:
            d.text((M, y), library.period_label, font=ctx.font_label, fill=st.pill)
            y += 60
        # 副副标题：日期范围
        date_range = _format_date_range(library.period_start, library.period_end)
        if date_range:
            d.text((M, y), date_range, font=ctx.font_song, fill=st.mist)
            y += 44
        y += 12

        # ── 空报告降级 ──
        if library.is_empty:
            y_mid = spec.height // 2 - 60
            d.text((M, y_mid), "暂无学习数据", font=font_title_big, fill=st.mist)
            d.text((M, y_mid + 80), "标记学会 / 练习打卡 让报告开始生成", font=ctx.font_song, fill=st.mist)
            return y_mid + 160

        # ── ② 核心数据 pill ──
        stats = [
            (f"练习 {library.total_practice_minutes} 分钟", st.pill, st.label),
            (f"打卡 {library.total_practice_sessions} 次", st.mist, st.text),
            (f"学会 {len(library.songs_learned)} 首", st.pill, st.label),
        ]
        if library.current_streak_days > 0:
            stats.append((f"连续 {library.current_streak_days} 天", st.mist, st.text))
        if library.longest_streak_days > 0:
            stats.append((f"最长 {library.longest_streak_days} 天", st.mist, st.text))
        stat_x = M
        for txt, bg, fg in stats:
            tw = d.textlength(txt, font=ctx.font_label) + 36
            d.rounded_rectangle((stat_x, y, stat_x + tw, y + 44),
                                radius=22, fill=bg)
            d.text((stat_x + 18, y + 4), txt, font=ctx.font_label, fill=fg)
            stat_x += tw + 12
        y += 60

        # 分隔线
        d.line((M, y, W - M, y), fill=st.line, width=2)
        y += 16

        # ── ③ 本月新学列表 ──
        songs_learned = library.songs_learned
        if songs_learned:
            y = self._draw_section_label(
                ctx, M, y, f"✓ 本期新学 · {len(songs_learned)} 首",
            )
            for i, item in enumerate(songs_learned[:12], start=1):
                title = (item.get("title") or "（无题）").strip()
                learned_at = _format_date(item.get("learned_at", ""))
                artist = (item.get("artist") or "").strip()
                text = f"{title} · {artist}" if artist else title
                text = _truncate(text, W - 2 * M - 130, d, ctx.font_song)
                d.text((M, y), f"{i:02d}", font=ctx.font_song, fill=st.mist)
                tx = M + 50
                d.text((tx, y), text, font=ctx.font_song, fill=st.text)
                if learned_at:
                    ts = learned_at
                    tsw = d.textlength(ts, font=ctx.font_song)
                    d.text((W - M - tsw, y), ts, font=ctx.font_song, fill=st.mist)
                y += f_section + 4
                if y >= spec.height - margin - 100:
                    remain = len(songs_learned) - i
                    if remain > 0:
                        d.text((M, y), f"…还有 {remain} 首",
                               font=ctx.font_song, fill=st.mist)
                        y += 40
                    break
            y += 8

        # ── ④ Top 歌手 + 调性分布（左右双栏） ──
        if library.top_artists or library.key_buckets:
            y = self._draw_section_label(
                ctx, M, y, "★ 偏好画像",
            )
            col_w = (W - 2 * M - 30) // 2
            left_x = M
            right_x = M + col_w + 30

            # 左栏：Top 歌手
            if library.top_artists:
                d.text((left_x, y), "Top 歌手", font=ctx.font_song, fill=st.mist)
                y_inner = y + 44
                max_count = max((a.get("count", 0) for a in library.top_artists), default=0)
                for i, art in enumerate(library.top_artists[:top_n_artists]):
                    name = (art.get("name") or "—").strip()
                    count = int(art.get("count", 0))
                    text = _truncate(name, col_w - 100, d, ctx.font_song)
                    d.text((left_x, y_inner), text, font=ctx.font_song, fill=st.text)
                    # 简易条形
                    bar_max_w = 60
                    bar_w = int(bar_max_w * (count / max_count)) if max_count > 0 else 0
                    bar_y = y_inner + ctx.font_song.size // 2 - 3
                    d.rounded_rectangle(
                        (left_x + col_w - 100, bar_y,
                         left_x + col_w - 100 + bar_w, bar_y + 6),
                        radius=3, fill=st.pill,
                    )
                    # 数量
                    cnt = f"{count}"
                    cnw = d.textlength(cnt, font=ctx.font_song)
                    d.text((left_x + col_w - cnw, y_inner),
                           cnt, font=ctx.font_song, fill=st.mist)
                    y_inner += f_section + 2
                    if y_inner >= spec.height - margin - 60:
                        break

            # 右栏：调性分布
            if library.key_buckets:
                # 同步基线 = 左栏 y+0 同样的位置
                d.text((right_x, y), "调性分布", font=ctx.font_song, fill=st.mist)
                y_inner = y + 44
                max_count = max((b.get("count", 0) for b in library.key_buckets), default=0)
                for bucket in library.key_buckets[:8]:
                    label = (bucket.get("label") or "未标").strip()
                    count = int(bucket.get("count", 0))
                    text = _truncate(label, col_w - 100, d, ctx.font_song)
                    d.text((right_x, y_inner), text, font=ctx.font_song, fill=st.text)
                    # 简易条形
                    bar_max_w = 60
                    bar_w = int(bar_max_w * (count / max_count)) if max_count > 0 else 0
                    bar_y = y_inner + ctx.font_song.size // 2 - 3
                    d.rounded_rectangle(
                        (right_x + col_w - 100, bar_y,
                         right_x + col_w - 100 + bar_w, bar_y + 6),
                        radius=3, fill=st.pill,
                    )
                    cnt = f"{count}"
                    cnw = d.textlength(cnt, font=ctx.font_song)
                    d.text((right_x + col_w - cnw, y_inner),
                           cnt, font=ctx.font_song, fill=st.mist)
                    y_inner += f_section + 2
                    if y_inner >= spec.height - margin - 60:
                        break
            y = max(y_inner, y) + 12

        # ── ⑤ 完整时间线（最近练习） ──
        if show_timeline and library.recent_practice:
            recent = library.recent_practice
            y = self._draw_section_label(
                ctx, M, y, f"⏱ 最近练习 · {len(recent)} 次",
            )
            for i, item in enumerate(recent[:8], start=1):
                title = (item.get("title") or "（无题）").strip()
                minutes = int(item.get("minutes", 0))
                rating = int(item.get("self_rating", 0))
                occurred_at = _format_date(item.get("occurred_at", ""))
                # 时间戳放右边固定位置 + 自评星紧贴 + "歌名 · 分钟" 在左侧
                # 右侧：自评 + 时间戳 = 200px 范围
                # 左侧宽度 = W - 2*M - 220
                base = f"{title} · {minutes} 分钟"
                text = _truncate(base, W - 2 * M - 240, d, ctx.font_song)
                d.text((M, y), text, font=ctx.font_song, fill=st.text)
                # 自评
                if rating > 0:
                    rating_str = "★" * min(rating, 5)
                    d.text((W - M - 220, y), rating_str, font=ctx.font_song, fill=st.pill)
                # 时间戳
                if occurred_at:
                    ts = occurred_at
                    tsw = d.textlength(ts, font=ctx.font_song)
                    d.text((W - M - tsw, y), ts, font=ctx.font_song, fill=st.mist)
                y += f_section + 4
                if y >= spec.height - margin - 60:
                    remain = len(recent) - i
                    if remain > 0:
                        d.text((M, y), f"…还有 {remain} 次练习",
                               font=ctx.font_song, fill=st.mist)
                        y += 40
                    break
            y += 10

        # ── ⑥ 难度分布（如果有，作为底部辅助） ──
        if library.difficulty_buckets:
            y = self._draw_section_label(
                ctx, M, y, "难度分布",
            )
            max_count = max((b.get("count", 0) for b in library.difficulty_buckets), default=0)
            for bucket in library.difficulty_buckets:
                label = (bucket.get("label") or "未标").strip()
                count = int(bucket.get("count", 0))
                d.text((M, y), label, font=ctx.font_song, fill=st.text)
                # bar
                bar_max_w = W - 2 * M - 200
                bar_w = int(bar_max_w * (count / max_count)) if max_count > 0 else 0
                bar_y = y + ctx.font_song.size // 2 - 3
                d.rounded_rectangle(
                    (M + 80, bar_y, M + 80 + bar_w, bar_y + 6),
                    radius=3, fill=st.pill,
                )
                cnt = f"{count}"
                cnw = d.textlength(cnt, font=ctx.font_song)
                d.text((W - M - cnw, y), cnt, font=ctx.font_song, fill=st.mist)
                y += 32
                if y >= spec.height - margin:
                    break

        return y

    def _draw_section_label(self, ctx: DrawContext, x: int, y: int, text: str) -> int:
        """复用 ctx.draw_label 画分节标签。返回新的 y。"""
        ctx.draw_label(x, y, text)
        return y + ctx.font_label.size + 56
