"""P4 R2: PracticeApplicationService——打卡应用服务。

职责:
- 打卡 (log): 构造 PracticeLog + 写 FileEventStore (practice_logged)
- 重复幂等: event_id 去重, 相同 event_id 返回已有
- 统计计算: compute_stats / compute_streak / compute_month_summary
- 冷启动: 数据不足时不展示伪趋势, 只展示已知事实

错误映射:
- PracticeValidationFailed (400): minutes/rating/note 越界
- PracticeServiceError (500): 内部错误
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any, List, Mapping, Optional

from core.data.practice import (
    PracticeLog,
    PracticeStreak,
    PracticeMonthSummary,
    LearningStats,
    compute_month_summary,
    compute_stats,
    compute_streak,
)


class PracticeServiceError(Exception):
    """可由 HTTP 适配层稳定映射。"""


class PracticeValidationFailed(PracticeServiceError):
    pass


@dataclass(frozen=True)
class PracticeLogResult:
    log: PracticeLog
    already_processed: bool = False


class PracticeApplicationService:
    """打卡应用服务。

    构造时注入 event_store (FileEventStore) 与 song_repository (SongRepository)。
    所有打卡先走 EventStore 持久化, 再从事件流中重建内存汇总。
    """

    def __init__(self, *, event_store, song_repository=None):
        self._events = event_store
        self._songs = song_repository

    # ── 打卡 ──

    def log(self, payload: Mapping[str, Any]) -> PracticeLogResult:
        """记录一次练习打卡。

        幂等: 相同 event_id 重复提交 → 返回已有事件, already_processed=True。
        """
        log = PracticeLog(
            event_id=(payload.get("event_id") or f"evt_{uuid.uuid4().hex}").strip(),
            song_id=payload.get("song_id", ""),
            title_snapshot=payload.get("title_snapshot", ""),
            minutes=int(payload.get("minutes", 0)),
            self_rating=int(payload.get("self_rating", 0)),
            note=str(payload.get("note", "")).strip(),
            occurred_at=payload.get("occurred_at", ""),
            source=str(payload.get("source", "learning-ui")),
        )
        try:
            log.validate()
        except ValueError as exc:
            raise PracticeValidationFailed(str(exc)) from exc

        # 补全 title_snapshot
        if not log.title_snapshot and log.song_id and self._songs:
            lib = self._songs.load().value
            song = lib.get_by_id(log.song_id)
            if song:
                log = PracticeLog(
                    event_id=log.event_id,
                    song_id=log.song_id,
                    title_snapshot=song.title,
                    minutes=log.minutes,
                    self_rating=log.self_rating,
                    note=log.note,
                    occurred_at=log.occurred_at,
                    source=log.source,
                )

        # 事件写入 (FileEventStore.append_event 幂等)
        event = {
            "schema_version": 2,
            "event_id": log.event_id,
            "occurred_at": log.occurred_at or _today_iso(),
            "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "type": "practice_logged",
            "source": log.source,
            "song_id": log.song_id,
            "title_snapshot": log.title_snapshot,
            "meta": {
                "minutes": log.minutes,
                "self_rating": log.self_rating,
                "note": log.note,
            },
        }
        result = self._events.append(event)
        already = result.status == "already_exists"
        return PracticeLogResult(log=log, already_processed=already)

    # ── 读取 (从事件流重建) ──

    def get_all_logs(self) -> List[PracticeLog]:
        """从 EventStore 读全部 practice_logged 事件 → PracticeLog 列表。"""
        from server.ports.repositories import EventQuery
        logs = []
        for ev in self._events.iter(EventQuery(event_type="practice_logged")):
            meta = ev.get("meta", {})
            logs.append(PracticeLog(
                event_id=ev.get("event_id", ""),
                song_id=ev.get("song_id", ""),
                title_snapshot=ev.get("title_snapshot", ""),
                minutes=int(meta.get("minutes", 0)),
                self_rating=int(meta.get("self_rating", 0)),
                note=str(meta.get("note", "")),
                occurred_at=ev.get("occurred_at", ""),
                source=ev.get("source", ""),
            ))
        return logs

    def get_stats(self, *, today: Optional[str] = None) -> LearningStats:
        logs = self.get_all_logs()
        return compute_stats(logs, today=today)

    def get_streak(self, *, today: Optional[str] = None) -> PracticeStreak:
        logs = self.get_all_logs()
        return compute_streak(logs, today=today)

    def get_month_summary(self, month: str) -> PracticeMonthSummary:
        logs = self.get_all_logs()
        return compute_month_summary(month, logs)


def _today_iso() -> str:
    return date.today().isoformat() + "T00:00:00+08:00"
