"""场景预设（Preset）—— 用户的完整场景快照。

一个 Preset 可完整复现一次海报创作：
  SongQuery + Layout + Palette + Skin + Canvas + 参数 + 导出设置

存储位置：data/presets/{name}/preset.json + data/presets/manifest.json
"""
import json
import os
import re
import shutil
import unicodedata
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


# Song.id 格式（core/data/songs.py：song_<uuid hex>）。
# R0.5：custom_ids 只允许稳定 song_id，旧歌名集合由 migrate_custom_ids 处理。
SONG_ID_RE = re.compile(r"^song_[0-9a-f]{32}$")

CURRENT_SCHEMA_VERSION = 2  # v2：custom_ids 为 song_id[]；未匹配旧歌名隔离进 unresolved


def new_preset_id() -> str:
    """生成无业务含义的 Preset ID。"""
    return f"preset_{uuid.uuid4().hex[:16]}"


def is_valid_preset_id(preset_id: str) -> bool:
    """Preset ID 必须是单个安全路径段；兼容既有 test1/legacy1 等旧 ID。"""
    if not isinstance(preset_id, str) or not preset_id or len(preset_id) > 80:
        return False
    if preset_id != preset_id.strip() or preset_id in (".", ".."):
        return False
    if "/" in preset_id or "\\" in preset_id:
        return False
    return not any(ord(char) < 32 or ord(char) == 127 for char in preset_id)


@dataclass
class SongQuery:
    """歌曲选择快照，不是完整数据。"""
    status: str = "active"           # "active" | "draft" | "all"
    classify: str = "chars"          # "chars" | "artist" | "pinyin"
    sort_by: str = "default"         # "default" | "title" | "artist" | "added"
    max_songs: int = 0               # 0 = 不限
    custom_ids: list = field(default_factory=list)  # 手动集合：song_id 列表（R0.5）
    unresolved: list = field(default_factory=list)  # 迁移时未匹配的旧歌名（隔离可见，不丢）


def validate_song_query(sq: "SongQuery"):
    """拒绝重复或无效 ID。保存前调用，防止带病写入长期关系。"""
    seen = set()
    for item in sq.custom_ids:
        if not isinstance(item, str) or not SONG_ID_RE.match(item):
            raise ValueError(f"custom_ids 只接受稳定 song_id，收到：{item!r}")
        if item in seen:
            raise ValueError(f"custom_ids 存在重复 ID：{item}")
        seen.add(item)


def migrate_custom_ids(preset: "Preset", id_by_title: dict) -> dict:
    """把旧歌名 custom_ids 迁移为 song_id（契约 §4.3）。

    id_by_title: {NFC 规范化 title: song_id}（精确匹配）。
    已是合法 ID 的项保留并去重；歌名精确命中替换为 ID；
    未匹配项移入 song_query.unresolved（不静默丢失）。
    返回 {resolved: {title: id}, unresolved: [...], changed: bool}。
    """
    sq = preset.song_query
    resolved, unresolved, kept = {}, [], []
    changed = preset.schema_version < CURRENT_SCHEMA_VERSION
    for item in sq.custom_ids:
        if isinstance(item, str) and SONG_ID_RE.match(item):
            if item not in kept:
                kept.append(item)
            continue
        title = unicodedata.normalize("NFC", str(item or "")).strip()
        song_id = id_by_title.get(title)
        if song_id:
            resolved[title] = song_id
            if song_id not in kept:
                kept.append(song_id)
            changed = True
        else:
            if title and title not in unresolved and title not in sq.unresolved:
                unresolved.append(title)
            changed = True
    if len(kept) != len(sq.custom_ids):
        changed = True
    sq.custom_ids = kept
    for t in unresolved:
        sq.unresolved.append(t)
    if changed:
        preset.schema_version = CURRENT_SCHEMA_VERSION
    return {"resolved": resolved, "unresolved": unresolved, "changed": changed}


@dataclass
class Preset:
    """完整可重现场景。"""
    schema_version: int = CURRENT_SCHEMA_VERSION
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


def _ensure_dir(presets_dir: str):
    os.makedirs(presets_dir, exist_ok=True)


def _manifest_path(presets_dir: str):
    return os.path.join(presets_dir, "manifest.json")


def _preset_dir(presets_dir: str, preset_id: str):
    if not is_valid_preset_id(preset_id):
        raise ValueError(f"非法 preset_id：{preset_id!r}")
    return os.path.join(presets_dir, preset_id)


def init_presets(data_root: str):
    presets_dir = os.path.join(data_root, "presets")
    _ensure_dir(presets_dir)
    manifest = _load_manifest(presets_dir)
    if "_default" not in manifest:
        p = Preset.default()
        save(p, presets_dir)
    return presets_dir


def _load_manifest(presets_dir: str) -> dict:
    path = _manifest_path(presets_dir)
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_manifest(presets_dir: str, manifest: dict):
    with open(_manifest_path(presets_dir), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def list_all(presets_dir: str) -> list:
    manifest = _load_manifest(presets_dir)
    result = []
    for pid, info in manifest.items():
        info["id"] = pid
        result.append(info)
    result.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return result


def load(preset_id: str, presets_dir: str) -> Optional[Preset]:
    if not is_valid_preset_id(preset_id):
        return None
    manifest = _load_manifest(presets_dir)
    if preset_id not in manifest:
        return None
    path = os.path.join(_preset_dir(presets_dir, preset_id), "preset.json")
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return _from_dict(data)


def save(preset: Preset, presets_dir: str):
    _ensure_dir(presets_dir)
    if not is_valid_preset_id(preset.id):
        raise ValueError(f"非法 preset_id：{preset.id!r}")
    validate_song_query(preset.song_query)
    preset.updated_at = datetime.now().isoformat(timespec="seconds")
    d = _to_dict(preset)
    pdir = _preset_dir(presets_dir, preset.id)
    os.makedirs(pdir, exist_ok=True)
    with open(os.path.join(pdir, "preset.json"), "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    # 更新 manifest
    manifest = _load_manifest(presets_dir)
    manifest[preset.id] = {
        "name": preset.name,
        "layout_id": preset.layout_id,
        "is_default": preset.is_default,
        "created_at": preset.created_at,
        "updated_at": preset.updated_at,
    }
    _save_manifest(presets_dir, manifest)


def delete(preset_id: str, presets_dir: str) -> bool:
    """软删除：移入 .trash 子目录。返回预设是否存在过。"""
    if not is_valid_preset_id(preset_id):
        return False
    manifest = _load_manifest(presets_dir)
    pdir = _preset_dir(presets_dir, preset_id)
    existed = preset_id in manifest or os.path.isdir(pdir)
    if os.path.isdir(pdir):
        trash = os.path.join(presets_dir, ".trash")
        os.makedirs(trash, exist_ok=True)
        dst = os.path.join(trash, preset_id)
        i = 1
        while os.path.exists(dst):
            dst = os.path.join(trash, f"{preset_id}-{i}")
            i += 1
        shutil.move(pdir, dst)
    manifest.pop(preset_id, None)
    _save_manifest(presets_dir, manifest)
    return existed


def duplicate(preset_id: str, new_id: str, presets_dir: str,
              new_name: str = "") -> Optional[Preset]:
    if not is_valid_preset_id(new_id):
        raise ValueError(f"非法 preset_id：{new_id!r}")
    p = load(preset_id, presets_dir)
    if p is None:
        return None
    p.id = new_id
    p.name = new_name or f"{p.name} (副本)"
    p.created_at = datetime.now().isoformat(timespec="seconds")
    p.is_default = False
    save(p, presets_dir)
    return p


def _to_dict(p: Preset) -> dict:
    d = asdict(p)
    return d


def _from_dict(d: dict) -> Preset:
    """从 JSON dict 构造 Preset；容忍未知字段（前向兼容）与缺失字段（用默认值）。"""
    d = dict(d)
    sq = d.pop("song_query", {}) or {}
    preset_keys = {k for k in Preset.__dataclass_fields__ if k != "song_query"}
    p = Preset(**{k: v for k, v in d.items() if k in preset_keys})
    p.song_query = SongQuery(**{k: v for k, v in sq.items()
                                if k in SongQuery.__dataclass_fields__})
    return p
