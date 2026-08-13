"""主题加载器：扫描 themes/ 目录，读取每个 theme.json 构造成 Theme。

校验规则（来自 项目结构设计.md 3.3）：
- styles 必须含 5 个角色、两页齐全；RGBA 的 alpha 缺失默认 255。
- 背景文件不存在 → 该主题在列表中灰显（此处抛 ValueError，由调用方决定降级）。
- 新增主题 = 新建目录 + theme.json，App 重启或点「刷新」即出现，零代码改动。
"""
import json
import os
from typing import Dict

from .model import Theme, ThemeMetadata
from ..style import Style


def _to_style(d: dict) -> Style:
    return Style(
        text=tuple(d["text"]),
        label=tuple(d["label"]),
        pill=tuple(d["pill"]),
        line=tuple(d["line"]),
        mist=tuple(d["mist"]),
    )


def _to_metadata(d: dict) -> ThemeMetadata:
    """M3 P3 续：构造 ThemeMetadata（v1 兼容：空 dict → 默认 ThemeMetadata）。"""
    return ThemeMetadata(
        tags=tuple(d.get("tags", ())),
        scenes=tuple(d.get("scenes", ())),
        mood=d.get("mood", ""),
        language_friendly=d.get("language_friendly", "all"),
        song_count_range=tuple(d.get("song_count_range", (0, 9999))),
    )


def load_theme(theme_dir: str) -> Theme:
    cfg_path = os.path.join(theme_dir, "theme.json")
    if not os.path.isfile(cfg_path):
        raise ValueError(f"缺少 theme.json：{cfg_path}")
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    styles_raw = cfg.get("styles", {})
    styles = {}
    for page in ("1", "2"):
        if page not in styles_raw:
            raise ValueError(f"主题「{cfg['name']}」缺少第 {page} 页 styles")
        styles[int(page)] = _to_style(styles_raw[page])

    return Theme(
        name=cfg["name"],
        dir=theme_dir,
        output_prefix=cfg["output_prefix"],
        backgrounds=cfg.get("backgrounds", {}),
        watermark_fix=bool(cfg.get("watermark_fix", False)),
        styles=styles,
        font=cfg.get("font"),
        notes=cfg.get("notes", ""),
        # R4 Runtime v2 v2.5: theme 端能力声明（缺省 = 全部兼容）
        compatible_layouts=tuple(cfg.get("compatible_layouts", ())),
        # M3 P3 续: 智能推荐 metadata（缺省空 ThemeMetadata）
        metadata=_to_metadata(cfg.get("metadata", {})),
    )


def _to_metadata(d: dict) -> ThemeMetadata:
    """M3 P3 续：构造 ThemeMetadata（v1 兼容：空 dict → 默认 ThemeMetadata）。"""
    return ThemeMetadata(
        tags=tuple(d.get("tags", ())),
        scenes=tuple(d.get("scenes", ())),
        mood=d.get("mood", ""),
        language_friendly=d.get("language_friendly", "all"),
        song_count_range=tuple(d.get("song_count_range", (0, 9999))),
    )


def load_themes(themes_root: str) -> Dict[str, Theme]:
    """扫描 themes_root 下每个子目录（含 theme.json 的）加载为 Theme。"""
    themes: Dict[str, Theme] = {}
    if not os.path.isdir(themes_root):
        return themes
    for name in sorted(os.listdir(themes_root)):
        theme_dir = os.path.join(themes_root, name)
        if not os.path.isdir(theme_dir):
            continue
        if not os.path.isfile(os.path.join(theme_dir, "theme.json")):
            continue
        try:
            t = load_theme(theme_dir)
            themes[t.name] = t
        except ValueError as e:
            # 加载失败的主题不崩溃，记录后跳过（调用方可提示）
            print(f"[theme-loader] 跳过主题 {name}：{e}")
    return themes
