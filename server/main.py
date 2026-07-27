"""本地渲染后端（开发期）。

FastAPI 暴露渲染/主题/歌曲接口。前端（浏览器或后期 Electron BrowserWindow）连
http://localhost:8000 调用。MVP 后期由 Electron 把本服务打包为 child_process。

运行（项目根目录下）：
    pip install -r requirements.txt
    uvicorn server.main:app --reload --port 8000
"""

import io
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import replace, asdict
from datetime import datetime

from fastapi import FastAPI, Response, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.spec import CANVAS_PRESETS, AVOID_ZONES_X0, AVOID_ZONES_Y0, AVOID_ZONES_X1
from core.themes.loader import load_themes
from core.layouts import get_layout, list_layouts, layout_params
from core.data.songs import SongLibrary, build_default_library
from core.data.events import EVENT_TYPES, append_event, iter_events, tail as events_tail
from core.data import tabs as tabs_store
from core.engine import render_page

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THEMES_DIR = os.path.join(ROOT, "themes")
FONT = os.path.join(ROOT, "fonts", "MaokenAssortedSans.ttf")

app = FastAPI(title="主播工作台 · 渲染后端")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 开发期放开；生产期收窄到 Electron 域名
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/bg", StaticFiles(directory=THEMES_DIR), name="theme_bg")

SONGS_JSON = os.path.join(ROOT, "data", "songs.json")
SETTINGS_PATH = os.path.join(ROOT, "data", "settings.json")
EVENTS_JSON = os.path.join(ROOT, "data", "events.jsonl")
TABS_DIR = os.path.join(ROOT, "data", "tabs")
os.makedirs(TABS_DIR, exist_ok=True)
app.mount("/tabs", StaticFiles(directory=TABS_DIR), name="song_tabs")
themes = load_themes(THEMES_DIR)
library = build_default_library(json_path=SONGS_JSON)

# ---- 应用设置（settings.json）----
DEFAULT_SETTINGS = {
    "output_dir": os.path.join(ROOT, "output"),
    "default_canvas": "抖音全屏 9:20",
    "default_theme": "海洋柔光",
    "font_path": FONT,
    "backup_count": 20,
    "render_threads": 1,
}

def _load_settings() -> dict:
    if os.path.isfile(SETTINGS_PATH):
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return {**DEFAULT_SETTINGS, **json.load(f)}
    return DEFAULT_SETTINGS.copy()

def _save_settings(s: dict):
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)

settings = _load_settings()


@app.get("/api/health")
def health():
    return {"ok": True, "themes": len(themes), "songs": len(library.mastered())}


@app.get("/api/themes")
def api_themes():
    return [{"name": t.name, "prefix": t.output_prefix,
             "watermark_fix": t.watermark_fix,
             "backgrounds": t.backgrounds,
             "notes": t.notes} for t in themes.values()]


@app.get("/api/thumb/{theme_name}")
def api_thumb(theme_name: str):
    """主题列表缩略图：第 1 页背景缩到宽 360，JPEG + 内存缓存（主题不变不用失效）。"""
    if theme_name in _THUMB_CACHE:
        return Response(content=_THUMB_CACHE[theme_name], media_type="image/jpeg")
    t = themes.get(theme_name)
    if t is None:
        return Response("主题不存在", status_code=404)
    bg = t.backgrounds.get("1")
    path = os.path.join(THEMES_DIR, theme_name, bg) if bg else ""
    if not bg or not os.path.isfile(path):
        return Response("背景不存在", status_code=404)
    from PIL import Image
    im = Image.open(path).convert("RGB")
    im.thumbnail((360, 1080))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=80)
    data = buf.getvalue()
    _THUMB_CACHE[theme_name] = data
    return Response(content=data, media_type="image/jpeg")


_THUMB_CACHE: dict = {}


@app.get("/api/layouts")
def api_layouts():
    return list_layouts()

@app.get("/api/layouts/{layout_id}/params")
def api_layout_params(layout_id: str):
    try:
        return layout_params(layout_id)
    except KeyError as e:
        return Response(str(e), status_code=404)


@app.get("/api/songs")
def api_songs():
    return {"total": len(library.mastered()),
            "by_len": _count_by_len()}


def _song_dict(s) -> dict:
    """歌曲的完整可编辑字段视图（/api/songs/list 与编辑对话框用）。"""
    return {"title": s.title, "status": s.status, "section": s.section,
            "artists": s.artists, "lyricist": s.lyricist, "composer": s.composer,
            "key": s.key, "capo": s.capo, "difficulty": s.difficulty,
            "tabs": s.tabs, "tags": s.tags, "pinyin": s.pinyin,
            "added_at": s.added_at, "notes": s.notes,
            "learned_at": s.learned_at, "tab_files": s.tab_files}


@app.get("/api/songs/list")
def api_songs_list(status: str = None):
    """返回完整歌曲列表（含全部可编辑字段），可按 status 过滤（active/draft）。"""
    songs = library.songs
    if status:
        songs = [s for s in songs if s.status == status]
    return {"total": len(songs),
            "active": library.count_active(),
            "draft": library.count_draft(),
            "songs": [_song_dict(s) for s in songs]}


def _save_library():
    """变更后统一落盘：原子写 + 自动备份（data/backups/，滚动保留）。"""
    backup_dir = os.path.join(ROOT, "data", "backups")
    library.save(SONGS_JSON, backup_dir=backup_dir,
                 backup_count=settings.get("backup_count", 20))


def _clean_song_fields(payload: dict) -> dict:
    """清洗编辑/新增提交的字段：类型矫正 + 范围约束。"""
    fields = {}
    for k in SongLibrary.EDITABLE_FIELDS:
        if k not in payload:
            continue
        v = payload[k]
        if k in ("artists", "tags"):
            fields[k] = [str(x).strip() for x in (v or []) if str(x).strip()]
        elif k == "capo":
            fields[k] = None if v in (None, "") else max(0, min(12, int(v)))
        elif k == "section":
            fields[k] = None if v in (None, "") else max(1, min(7, int(v)))
        else:
            fields[k] = str(v).strip() if v is not None else ""
    if "title" in fields and not fields["title"]:
        raise ValueError("歌名不能为空")
    return fields


@app.post("/api/songs/status")
def api_songs_status(payload: dict):
    """切换歌曲状态：{"title": "知足", "status": "active"|"draft"}。

    一键「学会了」（draft→active）/「标回未会」（active→draft）。
    变更即原子写落盘 + 自动备份；渲染端点每次新排文字层，无需缓存失效。
    """
    title = (payload.get("title") or "").strip()
    status = (payload.get("status") or "").strip()
    if status not in ("active", "draft"):
        return Response("status 必须是 active 或 draft", status_code=400)
    mark = library.mark_active if status == "active" else library.mark_draft
    if not mark(title):
        return Response(f"未找到歌曲：{title}", status_code=404)
    if status == "active":
        # 迁移 v4：「标记学会」顺手回填 learned_at（标回未会不清除，历史以事件流为准）
        song = library.get(title)
        if song is not None:
            song.learned_at = datetime.now().strftime("%Y-%m-%d")
    _save_library()
    append_event(EVENTS_JSON, "song_learned" if status == "active" else "song_unlearned",
                 title=title)
    return {"ok": True, "title": title, "status": status,
            "active": library.count_active(), "draft": library.count_draft()}


@app.post("/api/songs/update")
def api_songs_update(payload: dict):
    """编辑歌曲信息：{"title": "知足", "fields": {"key": "G", "capo": 2, ...}}。

    title 定位歌曲；fields 支持全部可编辑字段（含改名 title，会查重）。
    变更即落盘 + 备份。
    """
    title = (payload.get("title") or "").strip()
    try:
        fields = _clean_song_fields(payload.get("fields") or {})
        if not fields:
            return Response("fields 为空", status_code=400)
        old_song = library.get(title)
        old_view = _song_dict(old_song) if old_song else None
        ok = library.update(title, fields)
    except ValueError as e:
        return Response(str(e), status_code=400)
    if not ok:
        return Response(f"未找到歌曲：{title}", status_code=404)
    _save_library()
    song = library.get(fields.get("title", title))
    # 字段级 diff 记入事件流（更新记录 feed 用）
    changes = [{"field": k, "old": old_view.get(k), "new": song and _song_dict(song).get(k)}
               for k in fields if old_view and old_view.get(k) != _song_dict(song).get(k)]
    append_event(EVENTS_JSON, "song_edited", title=song.title,
                 meta={"changes": changes})
    return {"ok": True, "song": _song_dict(song)}


@app.post("/api/songs/add")
def api_songs_add(payload: dict):
    """新增歌曲。title 必填且查重；status 默认 draft（学会后再上海报）。

    pinyin 留空则自动生成拼音首字母；added_at 自动填当天。
    """
    try:
        fields = _clean_song_fields(payload)
    except (ValueError, TypeError) as e:
        return Response(str(e), status_code=400)
    title = fields.pop("title", "")
    if not title:
        return Response("歌名不能为空", status_code=400)
    from core.data.songs import Song, pinyin_initials
    song = Song(title=title,
                status=payload.get("status") if payload.get("status") in ("active", "draft") else "draft",
                added_at=datetime.now().strftime("%Y-%m-%d"),
                **fields)
    if not song.pinyin:
        song.pinyin = pinyin_initials(title)
    if not library.add(song):
        return Response(f"歌曲已存在：{title}", status_code=409)
    _save_library()
    append_event(EVENTS_JSON, "song_added", title=title, meta={"status": song.status})
    return {"ok": True, "song": _song_dict(song),
            "active": library.count_active(), "draft": library.count_draft()}


@app.post("/api/songs/delete")
def api_songs_delete(payload: dict):
    """删除歌曲：{"title": "知足"}。变更即落盘 + 备份。"""
    title = (payload.get("title") or "").strip()
    if not library.remove(title):
        return Response(f"未找到歌曲：{title}", status_code=404)
    _save_library()
    append_event(EVENTS_JSON, "song_deleted", title=title)
    return {"ok": True, "title": title,
            "active": library.count_active(), "draft": library.count_draft()}


# ---- 曲谱附件（data/tabs/，文件挂 /tabs 静态路由）----
@app.post("/api/songs/{title}/tabs")
async def api_tab_upload(title: str, file: UploadFile = File(...)):
    """上传曲谱文件（图片/PDF，≤10MB）。落盘 data/tabs/{歌名}/ 并登记 tab_files。"""
    song = library.get(title)
    if song is None:
        return Response(f"未找到歌曲：{title}", status_code=404)
    data = await file.read()
    try:
        rel = tabs_store.save_tab(TABS_DIR, title, file.filename or "tab.png", data)
    except ValueError as e:
        return Response(str(e), status_code=400)
    song.tab_files.append(rel)
    _save_library()
    append_event(EVENTS_JSON, "song_edited", title=title,
                 meta={"changes": [{"field": "tab_files", "old": None, "new": rel}]})
    return {"ok": True, "file": rel, "tab_files": song.tab_files}


@app.get("/api/songs/{title}/tabs")
def api_tab_list(title: str):
    """列出歌曲的曲谱文件（相对路径，前端拼 / 前缀访问）。"""
    song = library.get(title)
    if song is None:
        return Response(f"未找到歌曲：{title}", status_code=404)
    return {"title": title, "tab_files": song.tab_files}


@app.delete("/api/songs/{title}/tabs")
def api_tab_delete(title: str, file: str):
    """删除曲谱文件：?file=tabs/知足/主歌.png。同时清登记与磁盘文件。"""
    song = library.get(title)
    if song is None:
        return Response(f"未找到歌曲：{title}", status_code=404)
    if file not in song.tab_files:
        return Response(f"曲谱不存在：{file}", status_code=404)
    song.tab_files.remove(file)
    tabs_store.delete_tab(TABS_DIR, title, file)
    _save_library()
    append_event(EVENTS_JSON, "song_edited", title=title,
                 meta={"changes": [{"field": "tab_files", "old": file, "new": None}]})
    return {"ok": True, "tab_files": song.tab_files}


# ---- 导出 ----
@app.post("/api/export")
def api_export(theme: str, page: int = 1,
               canvas: str = "标准 9:16", avoid: bool = False,
               layout: str = "grid-wrap",
               margin: int = None, font_song: int = None,
               row_h: int = None, sec_gap: int = None):
    """导出单页 PNG 到输出目录，返回文件路径。"""
    if theme not in themes:
        return Response(f"未知主题：{theme}", status_code=404)
    try:
        layout_plugin = get_layout(layout)
    except KeyError as e:
        return Response(str(e), status_code=404)
    base = CANVAS_PRESETS.get(canvas, CANVAS_PRESETS["标准 9:16"])
    spec = base
    if avoid:
        spec = replace(spec, avoid_zones=((AVOID_ZONES_X0, AVOID_ZONES_Y0, AVOID_ZONES_X1, base.height),))
    overrides = {k: v for k, v in
                 {"margin": margin, "font_song": font_song,
                  "row_h": row_h, "sec_gap": sec_gap}.items()
                 if v is not None}
    if overrides:
        spec = replace(spec, **overrides)

    t0 = time.perf_counter()
    img = render_page(themes[theme], layout_plugin, library, spec, page, FONT)
    duration = time.perf_counter() - t0

    # 输出命名：{prefix}-{layout_id}-{tag}-{page}.png
    tag = "糖圆体全屏绕排" if avoid and spec.height > 1920 else "糖圆体"
    filename = f"{themes[theme].output_prefix}-{layout}-{tag}-{page}.png"
    out_dir = settings["output_dir"]
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, filename)
    img.save(out_path, "PNG")

    append_event(EVENTS_JSON, "poster_exported", meta={
        "theme": theme, "layout": layout, "canvas": canvas, "page": page,
        "duration_ms": round(duration * 1000, 1)})
    return {"ok": True, "path": out_path, "filename": filename,
            "duration_ms": round(duration * 1000, 1)}


# ---- 批量导出任务（后台线程 + 进度查询）----
_EXPORT_JOBS: dict = {}


def _run_batch_job(job_id: str, layout_plugin, spec, out_dir: str):
    job = _EXPORT_JOBS[job_id]
    t0 = time.perf_counter()
    try:
        for tname, theme in themes.items():
            for page in range(1, (layout_plugin.pages or 2) + 1):
                job["current"] = f"{tname} p{page}"
                img = render_page(theme, layout_plugin, library, spec, page, FONT)
                tag = "糖圆体全屏绕排" if spec.avoid_zones and spec.height > 1920 else "糖圆体"
                filename = f"{theme.output_prefix}-{layout_plugin.id}-{tag}-{page}.png"
                out_path = os.path.join(out_dir, filename)
                img.save(out_path, "PNG")
                job["files"].append({"theme": tname, "page": page, "path": out_path})
                job["done"] += 1
        job["status"] = "done"
        job["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        # 批量导出按任务记一条事件（14 张图一条，不刷屏）
        append_event(EVENTS_JSON, "poster_exported", meta={
            "batch": True, "files": len(job["files"]), "total_ms": job["total_ms"]})
    except Exception as e:  # 任务失败也要让前端能查到
        job["status"] = "error"
        job["error"] = str(e)
    if job["total_ms"] is None:
        job["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)


@app.post("/api/export/batch")
def api_export_batch(layout: str = "grid-wrap",
                     canvas: str = "抖音全屏 9:20", avoid: bool = True):
    """启动批量导出（当前排版 × 全部主题 × 全部页）。

    立即返回 job_id，后台线程渲染；前端轮询 /api/export/jobs/{job_id}
    获取进度（done/total/current/status）。
    """
    try:
        layout_plugin = get_layout(layout)
    except KeyError as e:
        return Response(str(e), status_code=404)
    base = CANVAS_PRESETS.get(canvas, CANVAS_PRESETS["抖音全屏 9:20"])
    spec = base
    if avoid:
        spec = replace(spec, avoid_zones=((AVOID_ZONES_X0, AVOID_ZONES_Y0, AVOID_ZONES_X1, base.height),))

    out_dir = settings["output_dir"]
    os.makedirs(out_dir, exist_ok=True)
    pages = layout_plugin.pages or 2
    job_id = uuid.uuid4().hex[:8]
    _EXPORT_JOBS[job_id] = {
        "status": "running", "done": 0, "total": len(themes) * pages,
        "current": "", "files": [], "output_dir": out_dir,
        "total_ms": None, "error": None,
    }
    threading.Thread(target=_run_batch_job,
                     args=(job_id, layout_plugin, spec, out_dir),
                     daemon=True).start()
    return {"ok": True, "job_id": job_id, "total": len(themes) * pages}


@app.get("/api/export/jobs/{job_id}")
def api_export_job(job_id: str):
    """查询批量导出任务进度。"""
    job = _EXPORT_JOBS.get(job_id)
    if job is None:
        return Response(f"未知任务：{job_id}", status_code=404)
    return job


@app.post("/api/export/open")
def api_export_open():
    """在系统文件管理器中打开输出目录（macOS Finder / Windows 资源管理器）。"""
    out_dir = settings["output_dir"]
    os.makedirs(out_dir, exist_ok=True)
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", out_dir])
        elif sys.platform.startswith("win"):
            subprocess.Popen(["explorer", out_dir])
        else:
            subprocess.Popen(["xdg-open", out_dir])
    except Exception as e:
        return Response(f"打开目录失败：{e}", status_code=500)
    return {"ok": True, "output_dir": out_dir}


# ---- 事件流（更新记录 feed；统计聚合在 S5 阶段加 /api/stats/*）----
@app.get("/api/events")
def api_events(type: str = None, since: str = None, limit: int = 50):
    """事件 feed。默认返回最近 limit 条（倒序）；带 since 时返回该日期以来的正序全量（上限 500）。"""
    if type and type not in EVENT_TYPES:
        return Response(f"未知事件类型：{type}", status_code=400)
    limit = max(1, min(500, int(limit)))
    if since:
        events = list(iter_events(EVENTS_JSON, type=type, since=since))[:500]
    else:
        events = events_tail(EVENTS_JSON, n=limit, type=type)
    return {"total": len(events), "events": events}


# 客户端可上报的事件类型（曲库/导出事件由服务端自己写，不开放上报防伪造）
CLIENT_REPORTABLE = ("queue_added", "song_sung", "practice_logged")


@app.post("/api/events/report")
def api_events_report(payload: dict):
    """客户端行为上报（直播点歌/学歌打卡）：{"type": "song_sung", "title": "知足", "meta": {...}, "ts": 可选}。

    ts 用于离线补报时保留原始发生时刻；缺省为服务器当前时间。
    """
    etype = (payload.get("type") or "").strip()
    if etype not in CLIENT_REPORTABLE:
        return Response(f"不可上报的事件类型：{etype}（允许 {CLIENT_REPORTABLE}）", status_code=400)
    title = payload.get("title")
    if title is not None:
        title = str(title).strip() or None
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else None
    ts = payload.get("ts")
    ts = str(ts)[:19] if ts else None
    event = append_event(EVENTS_JSON, etype, title=title, meta=meta, ts=ts)
    return {"ok": True, "event": event}


# ---- 设置 ----
@app.get("/api/settings")
def api_settings_get():
    return settings


@app.post("/api/settings")
def api_settings_update(new_settings: dict):
    settings.update(new_settings)
    _save_settings(settings)
    return {"ok": True, "settings": settings}


@app.get("/api/render")
def api_render(theme: str, page: int = 1,
               canvas: str = "标准 9:16", avoid: bool = False,
               layout: str = "grid-wrap",
               margin: int = None, font_song: int = None,
               row_h: int = None, sec_gap: int = None):
    if theme not in themes:
        return Response(f"未知主题：{theme}", status_code=404)
    try:
        layout_plugin = get_layout(layout)
    except KeyError as e:
        return Response(str(e), status_code=404)
    base = CANVAS_PRESETS.get(canvas, CANVAS_PRESETS["标准 9:16"])
    spec = base
    if avoid:
        spec = replace(spec, avoid_zones=((AVOID_ZONES_X0, AVOID_ZONES_Y0, AVOID_ZONES_X1, base.height),))
    # 排版参数覆盖（对应插件 ParamSpec 的 key，未传则用预设默认值）
    overrides = {k: v for k, v in
                 {"margin": margin, "font_song": font_song,
                  "row_h": row_h, "sec_gap": sec_gap}.items()
                 if v is not None}
    if overrides:
        spec = replace(spec, **overrides)
    img = render_page(themes[theme], layout_plugin, library, spec, page, FONT)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return Response(buf.getvalue(), media_type="image/png")


def _count_by_len():
    out = {}
    for s in library.mastered():
        n = len(s.title)
        key = str(n) if n <= 6 else "7+"
        out[key] = out.get(key, 0) + 1
    return out
