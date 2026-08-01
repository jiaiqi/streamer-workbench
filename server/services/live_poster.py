"""R2.5 live-set 海报数据适配：把 LiveService 状态拍成 LiveSessionSnapshot。

不在 LiveService 内部塞海报相关代码——保持领域纯净。海报数据是「跨服务
编排」的产物，专门一个 helper 完成。

约束：
- 不修改 LiveService / LiveSessionPersistenceService 任何状态
- 只读
- song_id → Song 解析失败时退化（"歌名缺失"），不抛错
- 演唱会记录按 request_id 反查 request 拿 requester_name
"""
from __future__ import annotations

from typing import Optional

from core.layouts.live_set import LiveSessionSnapshot
from server.services.live import LiveService


def build_live_session_snapshot(
    live: LiveService,
    song_repository=None,
) -> LiveSessionSnapshot:
    """把 LiveService 状态拍成 live-set 用的 LiveSessionSnapshot。

    song_repository: 可选 SongRepository（用于 song_id → title/artist 解析）。
    不传时歌名退化显示"歌名缺失"。
    """
    session = live.session
    requests_dict = live.requests
    queue_entries = {e.request_id: e for e in live.queue_entries}
    performances_dict = live.performances

    # 反查歌名映射
    def _song_title(song_id: str) -> str:
        if song_repository is not None:
            try:
                snap = song_repository.load()
                if snap.value is not None:
                    by_id = {s.id: s for s in snap.value.songs}
                    song = by_id.get(song_id)
                    if song is not None and song.title.strip():
                        return song.title
            except Exception:
                pass
        return "歌名缺失"

    # 拼装 requests
    request_list = []
    for req in requests_dict.values():
        state = queue_entries[req.id].state if req.id in queue_entries else "queued"
        request_list.append({
            "id": req.id,
            "song_id": req.song_id,
            "song_title": _song_title(req.song_id),
            "requester_name": req.requester_name,
            "requested_at": req.requested_at,
            "entitlement_kind": req.entitlement_kind,
            "is_bumped": queue_entries[req.id].is_bumped if req.id in queue_entries else False,
            "state": state,
        })

    # 拼装 performances
    performance_list = []
    for perf in performances_dict.values():
        req = requests_dict.get(perf.request_id)
        performance_list.append({
            "request_id": perf.request_id,
            "song_id": perf.song_id,
            "song_title": _song_title(perf.song_id),
            "requester_name": req.requester_name if req else "",
            "result": perf.result,
            "performed_at": perf.performed_at or "",
            "reason": perf.reason,
        })

    return LiveSessionSnapshot(
        session_id=session.id,
        session_title=session.title,
        session_state=session.state,
        started_at=session.started_at,
        closed_at=session.closed_at,
        rule_version=session.rule_version,
        requests=tuple(request_list),
        performances=tuple(performance_list),
    )
