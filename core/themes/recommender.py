"""M3 P3 续：智能推荐主题算法。

输入：当前海报信息（title + 歌名列表 + 标签 + 数量）
输出：每套 theme 的得分 + top N 推荐

评分规则（启发式，简单可解释）：
  - 关键词命中（title/song_titles/tags 与 theme.metadata.tags 任一匹配）：+3/命中
  - 场景命中（scenes 与 theme.metadata.scenes 任一匹配，来源：用户标注）：+2/命中
  - mood 命中（单次）：+2
  - 歌曲数量在 song_count_range 内：+1；不在：-0.5（轻扣，避免 0 分）

排名取 top N（默认 3）。

零依赖，stdlib only。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence, Tuple

from .model import Theme


@dataclass(frozen=True)
class PosterContext:
    """M3 P3 续：海报上下文（推荐算法输入）。

    字段：
      title        海报标题（来自 poster.name）
      song_titles  歌曲标题列表
      tags         歌标签（可选；如有，纳入关键词匹配）
      scene        场景（可选；如有，纳入场景匹配，如 "直播"/"教学"/"弹唱"）
      song_count   歌曲数量
    """
    title: str = ""
    song_titles: Tuple[str, ...] = field(default_factory=tuple)
    tags: Tuple[str, ...] = field(default_factory=tuple)
    scene: str = ""
    song_count: int = 0

    def all_text(self) -> str:
        """合并 title + song_titles + tags 为一个字符串用于关键词匹配。"""
        return " ".join([self.title, *self.song_titles, *self.tags]).lower()


@dataclass(frozen=True)
class ThemeScore:
    """单个 theme 的推荐分数 + 命中明细。"""
    theme_name: str
    score: float
    tag_hits: int = 0
    scene_hits: int = 0
    mood_hit: bool = False
    count_in_range: bool = False

    def to_dict(self) -> dict:
        return {
            "theme_name": self.theme_name,
            "score": self.score,
            "tag_hits": self.tag_hits,
            "scene_hits": self.scene_hits,
            "mood_hit": self.mood_hit,
            "count_in_range": self.count_in_range,
        }


def _has_text(text: str, keyword: str) -> bool:
    """大小写不敏感的子串匹配。空 keyword 返 False。"""
    if not keyword:
        return False
    return keyword.lower() in text


def _normalize_mood(text: str) -> str:
    """粗粒度 mood 推断（无依赖启发式）。"""
    t = text.lower()
    if any(w in t for w in ("清新", "夏日", "明亮", "小清新", "fresh")):
        return "fresh"
    if any(w in t for w in ("深", "夜", "星", "deep")):
        return "deep"
    if any(w in t for w in ("可爱", "童", "软萌", "cute")):
        return "cute"
    if any(w in t for w in ("复古", "黑胶", "retro")):
        return "retro"
    if any(w in t for w in ("暖", "温柔", "治愈", "warm")):
        return "warm"
    if any(w in t for w in ("极简", "通透", "elegant")):
        return "elegant"
    return ""


def score_theme(theme: Theme, ctx: PosterContext) -> ThemeScore:
    """M3 P3 续：给单个 theme 算推荐分。"""
    meta = theme.metadata
    text = ctx.all_text()

    # 1. 关键词命中（title + song_titles + tags）
    tag_hits = sum(1 for kw in meta.tags if _has_text(text, kw))

    # 2. 场景命中（用户标注的场景 + 标题推断）
    scene_hits = 0
    if ctx.scene:
        for sc in meta.scenes:
            if _has_text(ctx.scene, sc):
                scene_hits += 1

    # 3. mood 匹配（粗推断）
    inferred_mood = _normalize_mood(text) if not ctx.scene else _normalize_mood(ctx.scene)
    mood_hit = bool(meta.mood) and meta.mood == inferred_mood

    # 4. 歌曲数量范围
    lo, hi = meta.song_count_range
    count_in_range = lo <= ctx.song_count <= hi

    # 总分（启发式权重）
    score = (
        tag_hits * 3
        + scene_hits * 2
        + (2 if mood_hit else 0)
        + (1 if count_in_range else -0.5)
    )

    return ThemeScore(
        theme_name=theme.name,
        score=score,
        tag_hits=tag_hits,
        scene_hits=scene_hits,
        mood_hit=mood_hit,
        count_in_range=count_in_range,
    )


def recommend_themes(
    themes: Sequence[Theme],
    ctx: PosterContext,
    top_n: int = 3,
) -> List[ThemeScore]:
    """M3 P3 续：给所有 theme 算分，按分数降序返 top N。"""
    scores = [score_theme(t, ctx) for t in themes]
    scores.sort(key=lambda s: (-s.score, s.theme_name))
    return scores[:top_n]


def recommend_themes_all(
    themes: Sequence[Theme],
    ctx: PosterContext,
) -> List[ThemeScore]:
    """M3 P3 续：算所有 theme 分数（不取 top N；UI 端可自己限制展示）。"""
    scores = [score_theme(t, ctx) for t in themes]
    scores.sort(key=lambda s: (-s.score, s.theme_name))
    return scores


__all__ = [
    "PosterContext",
    "ThemeScore",
    "score_theme",
    "recommend_themes",
    "recommend_themes_all",
]
