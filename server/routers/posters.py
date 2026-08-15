"""R1a.1 Poster HTTP 适配层（/api/posters*）。

路由表：
- GET    /api/posters              列出已保存海报摘要
- GET    /api/posters/special-stats R4 退出条件 #3：专用海报区日活
- POST   /api/posters              创建或覆盖更新（id 缺则生成）
- GET    /api/posters/{id}         读取完整 PosterDocument
- DELETE /api/posters/{id}         软删除
- POST   /api/posters/{id}/resolve 解析 SongSource → 歌曲快照列表
- GET    /api/posters/{id}/thumb   缩略图（?size=200|400|600，默认 200；M3 P1 快速预览）
- PATCH  /api/posters/{id}/name    inline 重命名
- POST   /api/posters/{id}/duplicate 复制（生成新 id + "(副本)" 名称）
- PATCH  /api/posters/{id}/order   拖拽排序：设置 order_index
- POST   /api/posters/batch        批量操作：action=delete|duplicate|set_theme

并发写由 expected_revision CAS 在 service 层处理；HTTP 层只做翻译。
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Query, Request, Response

from core.data.posters import PosterDocument
from server.api.errors import ApiError
from server.api.handlers import api_error_response
from server.api.secondary_models import (
    NamePatchRequest,
    OkResponse,
    PosterBatchRequest,
    PosterRequest,
    PosterResolveResponse,
    PosterResponse,
    PosterSaveResponse,
    PosterSummaryResponse,
    SpecialPosterDayBucket,
    SpecialPosterRecentEntry,
    SpecialPosterStatsResponse,
)
from server.dependencies import get_app_context
from server.ports.repositories import EventQuery
from server.services.posters import (
    PosterNotFound,
    PosterServiceError,
    PosterValidationFailed,
)

router = APIRouter()


def _payload_dict(payload) -> dict:
    return (payload.model_dump(exclude_unset=True)
            if hasattr(payload, "model_dump") else payload)


def _service_error(req: Request, error: PosterServiceError):
    if isinstance(error, PosterNotFound):
        status_code, code = 404, "poster_not_found"
    elif isinstance(error, PosterValidationFailed):
        status_code, code = 400, "invalid_poster"
    else:
        status_code, code = 500, "poster_error"
    return api_error_response(req, status_code, ApiError(code, str(error)))


@router.get("/api/posters", response_model=list[PosterSummaryResponse])
def api_posters_list(req: Request):
    items = get_app_context(req).poster_service.list()
    return [asdict(item) for item in items]


# ── R4 退出条件 #3：专用海报区日活 ──
#
# 必须在 /api/posters/{poster_id} 之前声明，否则 "special-stats" 会被
# FastAPI 当作 poster_id 解析。

_KIND_LIVE = "live-poster"
_KIND_REPORT = "learning-report"
_DAY_NAMES = {
    _KIND_LIVE: "live_poster",
    _KIND_REPORT: "learning_report",
}


@router.get("/api/posters/special-stats", response_model=SpecialPosterStatsResponse)
def api_posters_special_stats(
    req: Request,
    days: int = Query(30, ge=1, le=365, description="时间窗口天数，1 ~ 365"),
):
    """R4 退出条件 #3：专用海报区日活统计。

    事件源：events.jsonl 中 type=poster_exported 且 meta.kind ∈ {live-poster, learning-report}

    返回：
    - totals：总数（按 kind 区分）
    - by_day：按日分桶（"YYYY-MM-DD" → {live_poster, learning_report}）
    - recent：最近 5 条详情
    """
    ctx = get_app_context(req)
    when = datetime.now().astimezone()
    since_dt = when - timedelta(days=days)
    since = since_dt.isoformat(timespec="seconds")

    events = tuple(ctx.event_store.iter(
        EventQuery(event_type="poster_exported", since=since)
    ))

    totals: dict[str, int] = {"live_poster": 0, "learning_report": 0}
    by_day: dict[str, SpecialPosterDayBucket] = {}
    recent: list[SpecialPosterRecentEntry] = []

    for event in events:
        meta = event.get("meta") or {}
        kind = meta.get("kind", "")
        if kind not in _DAY_NAMES:
            continue  # 非专用海报（grid-export 等）不计入
        day_key = (event.get("occurred_at") or "")[:10]  # YYYY-MM-DD
        if not day_key:
            continue
        day_bucket = by_day.setdefault(day_key, SpecialPosterDayBucket())
        if kind == _KIND_LIVE:
            totals["live_poster"] += 1
            day_bucket.live_poster += 1
        else:
            totals["learning_report"] += 1
            day_bucket.learning_report += 1

        if len(recent) < 5:
            recent.append(SpecialPosterRecentEntry(
                event_id=event.get("event_id", ""),
                occurred_at=event.get("occurred_at", ""),
                kind=kind,
                title=meta.get("title", "") if kind == _KIND_LIVE else meta.get("period_label", ""),
                session_id=meta.get("session_id", "") if kind == _KIND_LIVE else "",
                days=meta.get("days", 0) if kind == _KIND_REPORT else 0,
                period_label=meta.get("period_label", "") if kind == _KIND_REPORT else "",
                filename=meta.get("filename", ""),
            ))

    return SpecialPosterStatsResponse(
        days=days,
        since=since,
        totals=totals,
        by_day=by_day,
        recent=recent,
    )


@router.get("/api/posters/{poster_id}", response_model=PosterResponse)
def api_posters_get(poster_id: str, req: Request):
    """完整 PosterDocument + revision。revision 用于客户端 CAS 自动保存。"""
    try:
        poster, revision = get_app_context(req).poster_service.get_with_revision(poster_id)
    except PosterServiceError as error:
        return _service_error(req, error)
    payload = poster.to_dict()
    payload["revision"] = revision
    return payload


@router.post("/api/posters", response_model=PosterSaveResponse)
def api_posters_save(payload: PosterRequest, req: Request):
    """创建或整体覆盖：id 缺则生成，否则按 repository CAS 更新。"""
    try:
        result = get_app_context(req).poster_service.save(_payload_dict(payload))
    except PosterServiceError as error:
        return _service_error(req, error)
    return {
        "ok": True,
        "id": result.poster.id,
        "revision": result.revision,
        "updated_at": result.poster.updated_at,
    }


@router.delete("/api/posters/{poster_id}", response_model=OkResponse)
def api_posters_delete(poster_id: str, req: Request):
    try:
        get_app_context(req).poster_service.delete(poster_id)
    except PosterServiceError as error:
        return _service_error(req, error)
    return {"ok": True}


@router.post(
    "/api/posters/{poster_id}/resolve",
    response_model=PosterResolveResponse,
)
def api_posters_resolve(poster_id: str, req: Request):
    """将已保存 Poster 的 SongSource + selected_song_ids 解析为不可变快照列表。

    预览与导出共享此结果；missing_song_ids 报告不在曲库的 song_id 引用。
    """
    try:
        result = get_app_context(req).poster_service.resolve(poster_id)
    except PosterServiceError as error:
        return _service_error(req, error)
    return {
        "poster_id": poster_id,
        "songs": [
            {
                "id": snap.id,
                "title": snap.title,
                "artists": list(snap.artists),
                "section": snap.section,
            }
            for snap in result.songs
        ],
        "missing_song_ids": list(result.missing_song_ids),
    }


# ── M3 海报 UI/UX（P0 缩略图 + 重命名 + 复制） ──────────────────────────

THUMB_SIZE = (200, 200)
THUMB_QUALITY = 85  # JPEG 质量（如果用 JPEG；当前 PIL PNG 不需要）

# M3 P1 快速预览放大镜：支持 200 / 400 / 600 三档
# 200 走磁盘缓存（.thumb.png），400 / 600 走内存即时放大（不落盘避免大文件占盘）
THUMB_PREVIEW_SIZES = {200, 400, 600}
THUMB_DEFAULT_PREVIEW = 400  # hover 浮层默认尺寸


def _thumb_path(paths, poster_id: str) -> Path:
    """缩略图缓存路径：data/posters/{id}/.thumb.png。"""
    return paths.posters_dir / poster_id / ".thumb.png"


def _generate_thumb(req: Request, poster_id: str) -> bytes:
    """懒生成 200x200 缩略图并落盘；返回 PNG bytes。"""
    context = get_app_context(req)
    try:
        poster, _ = context.poster_service.get_with_revision(poster_id)
    except PosterServiceError as error:
        raise error
    # 解析 SongSource → snapshot
    try:
        _poster, _full_lib, poster_lib, _missing = (
            context.poster_service.resolve_for_render(poster_id))
    except PosterServiceError as error:
        raise error
    # 选主题：取 layout_id 默认（grid-wrap 用第一个 theme 作 fallback）
    themes = context.themes
    # 取 poster 自己声明的主题；如果解析失败用第一个
    theme_id = poster.theme_id or (next(iter(themes)) if themes else None)
    if not theme_id or theme_id not in themes:
        if themes:
            theme_id = next(iter(themes))
        else:
            return b""
    theme = themes[theme_id]
    # 选 layout
    from core.layouts import get_layout
    try:
        layout = get_layout(poster.layout_id)
    except KeyError:
        layout = get_layout("grid-wrap")
    # 渲染第一页（render_page 接受 SongLibrary 本身）
    from core.engine import render_page
    from core.spec import get_canvas_spec
    from PIL import Image as _PILImage
    spec = get_canvas_spec("抖音全屏 9:20", avoid=True)
    img = render_page(theme, layout, poster_lib, spec, page=1,
                      font_path=str(context.paths.fonts_dir / "MaokenAssortedSans.ttf"))
    # 等比缩放到 200x200（cover 模式：填满 + 中心裁剪）
    img.thumbnail(THUMB_SIZE, _PILImage.Resampling.LANCZOS)
    buf = BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


@router.get(
    "/api/posters/{poster_id}/thumb",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}},
)
def api_poster_thumb(poster_id: str, req: Request, size: int = 200):
    """返回缩略图（PNG）。?size=200|400|600，默认 200（M3 P1 快速预览放大镜）。

    缓存策略：
    - 200 走磁盘缓存 data/posters/{id}/.thumb.png + mtime 失效
    - 400/600 从 200 缓存即时放大（不落盘，避免大文件占盘）

    设计权衡：
    - 不缓存大尺寸 → 重新放大耗时 < 50ms（200 缓存是 200x200，4 倍面积放大很快）
    - 不支持 600+ → 避免无限尺寸爆炸；用户真要看 1080p 全图直接渲染整张
    """
    from PIL import Image
    # size 参数白名单校验：非法值兜底到 200
    if size not in THUMB_PREVIEW_SIZES:
        size = 200
    context = get_app_context(req)
    paths = context.paths
    thumb = _thumb_path(paths, poster_id)
    poster_json = paths.posters_dir / poster_id / "poster.json"
    # 缓存命中：thumb 存在 + 不比 poster.json 旧
    if thumb.exists() and poster_json.exists() and thumb.stat().st_mtime >= poster_json.stat().st_mtime:
        cached = thumb.read_bytes()
        if size == 200:
            return Response(cached, media_type="image/png",
                            headers={"Cache-Control": "public, max-age=86400"})
        # 大尺寸：内存即时放大
        enlarged = _enlarge_thumb(cached, size)
        if enlarged is None:
            return Response(cached, media_type="image/png",
                            headers={"Cache-Control": "public, max-age=86400"})
        return Response(enlarged, media_type="image/png",
                        headers={"Cache-Control": "public, max-age=86400"})
    # 缓存失效或不存在：重新生成 200
    try:
        png_bytes = _generate_thumb(req, poster_id)
    except PosterNotFound as error:
        return _service_error(req, error)
    except Exception as error:
        return api_error_response(
            req, 500,
            ApiError("thumb_generate_failed", f"缩略图生成失败: {error}"))
    if not png_bytes:
        return api_error_response(
            req, 500,
            ApiError("thumb_generate_failed", "无可用主题渲染缩略图"))
    # 落盘缓存（200 永远落盘；400/600 永不落盘）
    try:
        thumb.parent.mkdir(parents=True, exist_ok=True)
        thumb.write_bytes(png_bytes)
    except OSError:
        # 缓存写入失败（只读盘？）不阻塞响应
        pass
    if size == 200:
        return Response(png_bytes, media_type="image/png",
                        headers={"Cache-Control": "public, max-age=86400"})
    # 大尺寸：内存即时放大
    enlarged = _enlarge_thumb(png_bytes, size)
    if enlarged is None:
        return Response(png_bytes, media_type="image/png",
                        headers={"Cache-Control": "public, max-age=86400"})
    return Response(enlarged, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


def _enlarge_thumb(png_bytes: bytes, size: int) -> bytes | None:
    """从 200 缓存即时放大到 size×size（LANCZOS 重采样）。

    返回 None 表示输入 PNG 解析失败（上层 fallback 返原图）。
    """
    from PIL import Image
    try:
        img = Image.open(BytesIO(png_bytes))
        img.load()
        img = img.convert("RGBA")
        img = img.resize((size, size), Image.Resampling.LANCZOS)
        buf = BytesIO()
        img.save(buf, "PNG", optimize=True)
        return buf.getvalue()
    except Exception:
        return None


@router.patch("/api/posters/{poster_id}/name", response_model=OkResponse)
def api_poster_rename(poster_id: str, payload: NamePatchRequest, req: Request):
    """inline 重命名：仅修改 name 字段，不动其他内容。

    用 expected_revision CAS 防并发覆盖；客户端必须先 GET 拿当前 revision。
    """
    try:
        context = get_app_context(req)
        poster, revision = context.poster_service.get_with_revision(poster_id)
        # 构造新 document（仅 name 改）
        new_payload = poster.to_dict()
        new_payload["name"] = payload.name
        if payload.revision is not None:
            new_payload["revision"] = payload.revision
        result = context.poster_service.save(new_payload)
        # 失效缩略图缓存（虽然 thumb 是按 poster.json mtime 触发，但 rename 不会改 mtime）
        # 实际上重命名不应失效缩略图，skip
    except PosterServiceError as error:
        return _service_error(req, error)
    return {"ok": True, "id": result.poster.id,
            "revision": result.revision, "name": result.poster.name}


@router.post(
    "/api/posters/{poster_id}/duplicate",
    response_model=PosterSaveResponse,
)
def api_poster_duplicate(poster_id: str, req: Request):
    """复制当前海报：生成新 id + name 追加「(副本)」。"""
    try:
        context = get_app_context(req)
        poster, _ = context.poster_service.get_with_revision(poster_id)
        new_payload = poster.to_dict()
        # 移除 id 让 service 生成新 id
        new_payload.pop("id", None)
        new_payload["revision"] = None
        new_payload["name"] = f"{poster.name}（副本）"
        result = context.poster_service.save(new_payload)
    except PosterServiceError as error:
        return _service_error(req, error)
    return {
        "ok": True,
        "id": result.poster.id,
        "revision": result.revision,
        "updated_at": result.poster.updated_at,
    }


# ── M3 海报 UI/UX（P1 批量操作） ────────────────────────────────

@router.post("/api/posters/batch")
def api_poster_batch(payload: PosterBatchRequest, req: Request):
    """M3 P1 批量操作。

    行为：
    - delete: 逐个调 delete；返回 {ok, deleted, failed}
    - duplicate: 逐个 save_payload（id 移除 + 名称追加「(副本)」）；返回 {ok, duplicated, new_ids, failed}
    - set_theme: 逐个 update theme_id；返回 {ok, updated, failed}

    设计权衡：
    - 顺序执行而非并发（避免磁盘 IO 尖峰；单 batch < 200 个，体感 < 5s）
    - 部分失败不中断后续（容错）；failed 数组逐个记录
    - 错误码 422 = 整批参数错（ids 全非法 / set_theme 缺 theme）
    """
    import re as _re
    context = get_app_context(req)
    payload_dict = _payload_dict(payload)
    action = payload_dict["action"]
    ids = payload_dict["ids"]
    theme = payload_dict.get("theme")
    poster_id_re = _re.compile(r"^[A-Za-z0-9_-]{1,64}$")  # 防御：只允许安全 id
    cleaned: list[str] = []
    for raw in ids:
        if isinstance(raw, str) and poster_id_re.match(raw):
            cleaned.append(raw)
    if not cleaned:
        return api_error_response(
            req, 422,
            ApiError("invalid_poster_ids", "ids 全部为非法 poster_id"))
    if action == "set_theme" and not theme:
        return api_error_response(
            req, 422,
            ApiError("missing_theme", "set_theme 必须提供 theme 字段"))
    failed: list[dict] = []
    succeeded_count = 0
    new_ids: list[str] = []
    for idx, pid in enumerate(cleaned):
        try:
            if action == "delete":
                context.poster_service.delete(pid)
                succeeded_count += 1
            elif action == "duplicate":
                poster, _rev = context.poster_service.get_with_revision(pid)
                new_payload = poster.to_dict()
                new_payload.pop("id", None)
                new_payload["revision"] = None
                new_payload["name"] = f"{poster.name}（副本）"
                r = context.poster_service.save(new_payload)
                new_ids.append(r.poster.id)
                succeeded_count += 1
            elif action == "set_theme":
                poster, _rev = context.poster_service.get_with_revision(pid)
                if not theme or theme not in context.themes:
                    failed.append({"id": pid, "error": f"未知主题: {theme!r}"})
                    continue
                updated = poster.to_dict()
                updated["revision"] = _rev
                updated["theme_id"] = theme
                context.poster_service.save(updated)
                succeeded_count += 1
            elif action == "reorder":
                # M3 P2: 按数组下标写入 order_index（i 越大越靠后；用 0-based 整数）
                poster, _rev = context.poster_service.get_with_revision(pid)
                updated = poster.to_dict()
                updated["revision"] = _rev
                updated["order_index"] = idx  # idx 是 enumerate 给的全局下标
                context.poster_service.save(updated)
                succeeded_count += 1
        except PosterNotFound:
            failed.append({"id": pid, "error": "not_found"})
        except PosterServiceError as error:
            failed.append({"id": pid, "error": str(error) or "service_error"})
        except Exception as error:  # noqa: BLE001  (单元素失败不中断整批)
            failed.append({"id": pid, "error": str(error) or "unknown_error"})
    result: dict = {"ok": True, "action": action}
    if action == "delete":
        result["deleted"] = succeeded_count
    elif action == "duplicate":
        result["duplicated"] = succeeded_count
        result["new_ids"] = new_ids
    elif action == "set_theme":
        result["updated"] = succeeded_count
    elif action == "reorder":
        result["reordered"] = succeeded_count
    result["failed"] = failed
    return result

