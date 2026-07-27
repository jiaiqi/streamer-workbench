"""场景预设（Preset）—— 用户的完整场景快照。

一个 Preset 可完整复现一次海报创作：
  SongQuery + Layout + Palette + Skin + Canvas + 参数 + 导出设置

存储位置：data/presets/{name}/preset.json + data/presets/manifest.json
"""
import json
import os
import shutil
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


PRESETS_DIR = None  # 由 server 初始化时设置


@dataclass
class SongQuery:
    """歌曲选择快照，不是完整数据。"""
    status: str = "active"           # "active" | "draft" | "all"
    classify: str = "chars"          # "chars" | "artist" | "pinyin"
    sort_by: str = "default"         # "default" | "title" | "artist" | "added"
    max_songs: int = 0               # 0 = 不限
    custom_ids: list = field(default_factory=list)  # 手动歌名列表


@dataclass
class Preset:
    """完整可重现场景。"""
    schema_version: int = 1
    id: str = ""
    name: str = "未命名预设"
    created_at: str = ""
    updated_at: str = ""
    is_default: bool = False

    # 场景内容
    song_query: SongQuery = field(default_factory=SongQuery)
    layout_id: str = "grid-wrap"
    palette_id: str = ""
    skin_id: str = ""
    canvas: dict = field(default_factory=lambda: {"width": 1080, "height": 2400})
    params: dict = field(default_factory=dict)
    export: dict = field(default_factory=dict)

    # 覆盖（运行时覆盖，不影响 Palette/Skin 源文件）
    color_overrides: dict = field(default_factory=dict)

    @staticmethod
    def default() -> "Preset":
        now = datetime.now().isoformat(timespec="seconds")
        return Preset(
            id="_default",
            name="默认预设",
            created_at=now,
            updated_at=now,
            is_default=True,
        )


# ── 仓储 ──


def _ensure_dir():
    if PRESETS_DIR is None:
        raise RuntimeError("PRESETS_DIR 未初始化（server 启动时调用 init_presets()）")
    os.makedirs(PRESETS_DIR, exist_ok=True)


def _manifest_path():
    return os.path.join(PRESETS_DIR, "manifest.json")


def _preset_dir(preset_id: str):
    safe = preset_id.replace("/", "_").replace("\\", "_")
    return os.path.join(PRESETS_DIR, safe)


def init_presets(data_root: str):
    global PRESETS_DIR
    PRESETS_DIR = os.path.join(data_root, "presets")
    _ensure_dir()
    manifest = _load_manifest()
    if "_default" not in manifest:
        p = Preset.default()
        save(p)
    return PRESETS_DIR


def _load_manifest() -> dict:
    path = _manifest_path()
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_manifest(manifest: dict):
    with open(_manifest_path(), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def list_all() -> list:
    manifest = _load_manifest()
    result = []
    for pid, info in manifest.items():
        info["id"] = pid
        result.append(info)
    result.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return result


def load(preset_id: str) -> Optional[Preset]:
    manifest = _load_manifest()
    if preset_id not in manifest:
        return None
    path = os.path.join(_preset_dir(preset_id), "preset.json")
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return _from_dict(data)


def save(preset: Preset):
    _ensure_dir()
    preset.updated_at = datetime.now().isoformat(timespec="seconds")
    d = _to_dict(preset)
    pdir = _preset_dir(preset.id)
    os.makedirs(pdir, exist_ok=True)
    with open(os.path.join(pdir, "preset.json"), "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    # 更新 manifest
    manifest = _load_manifest()
    manifest[preset.id] = {
        "name": preset.name,
        "layout_id": preset.layout_id,
        "is_default": preset.is_default,
        "created_at": preset.created_at,
        "updated_at": preset.updated_at,
    }
    _save_manifest(manifest)


def delete(preset_id: str):
    """软删除：移入 .trash 子目录。"""
    pdir = _preset_dir(preset_id)
    if os.path.isdir(pdir):
        trash = os.path.join(PRESETS_DIR, ".trash")
        os.makedirs(trash, exist_ok=True)
        shutil.move(pdir, os.path.join(trash, preset_id))
    manifest = _load_manifest()
    manifest.pop(preset_id, None)
    _save_manifest(manifest)


def duplicate(preset_id: str, new_id: str, new_name: str = "") -> Optional[Preset]:
    p = load(preset_id)
    if p is None:
        return None
    p.id = new_id
    p.name = new_name or f"{p.name} (副本)"
    p.created_at = datetime.now().isoformat(timespec="seconds")
    p.is_default = False
    save(p)
    return p


def _to_dict(p: Preset) -> dict:
    d = asdict(p)
    return d


def _from_dict(d: dict) -> Preset:
    sq = d.pop("song_query", {})
    p = Preset(**d)
    p.song_query = SongQuery(**sq)
    return p
