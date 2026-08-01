"""事件日志层（追加式 JSONL）。

一切带时间维度的历史（曲库变更/学会/练习打卡/直播点歌/海报导出）都写成
data/events.jsonl 里的一行一个 JSON 对象：

    {"schema_version": 2, "event_id": "evt_...", "occurred_at": "...",
     "recorded_at": "...", "type": "song_learned", "song_id": "song_...",
     "title_snapshot": "凄美地", "source": "songs-api", "meta": {...}}

设计决策（design/roadmap-data-stats.md 第 3 节）：
  - songs.json 仍是当前状态的唯一真相；本文件只追加、不改写，专记历史；
  - append 模式 open-write-close，一行一事件，崩溃截断最多坏最后一行；
  - 统计只算不存：需要聚合时由 server 调 iter_events() 现算；
  - 撤退路线：事件量破万后可整体导入 SQLite，schema 不变。
"""
import json
import os
import threading
import uuid
from datetime import datetime
from typing import Iterator, Optional

# 事件类型白名单（新增类型需同步 design/roadmap-data-stats.md 第 4 节表格）
EVENT_TYPES = (
    "song_added", "song_deleted", "song_edited",
    "song_learned", "song_unlearned",
    "practice_logged",
    "queue_added", "song_sung",
    "poster_exported",
)

_EVENT_WRITE_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _normalize_timestamp(value: Optional[str]) -> str:
    """规范为带时区 ISO 时间；兼容旧客户端发送的无时区本地时间。"""
    if not value:
        return _now()
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as e:
        raise ValueError(f"无效事件时间：{value}") from e
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return parsed.isoformat(timespec="seconds")


def _find_event(path: str, event_id: str) -> Optional[dict]:
    if not os.path.isfile(path):
        return None
    for event in iter_events(path):
        if event.get("event_id") == event_id:
            return event
    return None


def append_event(path: str, type: str, title: Optional[str] = None,
                 meta: Optional[dict] = None, ts: Optional[str] = None,
                 *, song_id: Optional[str] = None,
                 title_snapshot: Optional[str] = None,
                 occurred_at: Optional[str] = None,
                 event_id: Optional[str] = None,
                 source: str = "server") -> dict:
    """向 events.jsonl 追加一个事件，返回写入的事件对象。

    type 必须在 EVENT_TYPES 白名单内（防手滑写出无法统计的类型名）。
    title/ts 是 Schema v1 调用兼容参数，新代码使用 title_snapshot/occurred_at。
    客户端补报必须复用 event_id；重复 event_id 返回已有事件，不重复追加。
    """
    if type not in EVENT_TYPES:
        raise ValueError(f"未知事件类型：{type}（白名单见 EVENT_TYPES）")
    event_id = (event_id or f"evt_{uuid.uuid4().hex}").strip()
    if not event_id:
        raise ValueError("event_id 不能为空")
    title_snapshot = title_snapshot if title_snapshot is not None else title
    occurred_at = _normalize_timestamp(occurred_at or ts)
    source = (source or "").strip()
    if not source:
        raise ValueError("source 不能为空")
    event = {
        "schema_version": 2,
        "event_id": event_id,
        "occurred_at": occurred_at,
        "recorded_at": _now(),
        "type": type,
        "source": source,
    }
    if song_id is not None:
        event["song_id"] = song_id
    if title_snapshot is not None:
        event["title_snapshot"] = title_snapshot
    if meta:
        event["meta"] = meta
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with _EVENT_WRITE_LOCK:
        existing = _find_event(path, event_id)
        if existing is not None:
            comparable = ("schema_version", "event_id", "occurred_at", "type", "source",
                          "song_id", "title_snapshot", "meta")
            if any(existing.get(key) != event.get(key) for key in comparable):
                raise ValueError(f"event_id 冲突且事件内容不同：{event_id}")
            return existing
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def iter_events(path: str, type: Optional[str] = None,
                since: Optional[str] = None,
                until: Optional[str] = None) -> Iterator[dict]:
    """顺序扫描事件流。文件不存在时返回空迭代。

    since/until 为 "YYYY-MM-DD" 或完整 ISO 时间串（字符串前缀比较即可，
    因 ts 格式固定为 %Y-%m-%dT%H:%M:%S）。坏行跳过（容忍崩溃截断）。
    """
    if not os.path.isfile(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if type and event.get("type") != type:
                continue
            occurred_at = event.get("occurred_at") or event.get("ts", "")
            if since and occurred_at < since:
                continue
            if until and occurred_at > until:
                continue
            yield event


def tail(path: str, n: int = 50, type: Optional[str] = None) -> list:
    """最近 n 条事件（倒序，最新在前）。更新记录 feed 用。"""
    events = list(iter_events(path, type=type))
    return events[::-1][:n]


# ── 聚合工具：连续天数 (R4.0 抽出，原 server/services/stats + learning_report 各实现一次) ──


def compute_streaks(dates: set[str]) -> tuple[int, int]:
    """从一组 ISO 日期（'YYYY-MM-DD' 或 ISO 时间前 10 字符）算连续打卡。

    返回 (current_streak, longest_streak)：
    - current_streak: 从今天往回数，最长连续多少天有打卡；今天没打卡则 = 0
    - longest_streak: 历史最长连续天数

    空集 → (0, 0)。

    R4.0 抽出：原 server/services/stats.py:_compute_streaks 和
    server/services/learning_report.py:_compute_streaks 各自实现一份，行为一致。
    抽到 core/data/events.py 后两边 import，确保学习报告和统计页 streak 一致。
    """
    if not dates:
        return (0, 0)
    from datetime import date as _date
    from datetime import timedelta
    sorted_dates = sorted(dates)
    longest = 1
    cur = 1
    for i in range(1, len(sorted_dates)):
        d_prev = _date.fromisoformat(sorted_dates[i - 1])
        d_cur = _date.fromisoformat(sorted_dates[i])
        if (d_cur - d_prev).days == 1:
            cur += 1
            longest = max(longest, cur)
        else:
            cur = 1
    today = _date.today()
    current = 0
    d = today
    while d.isoformat() in dates:
        current += 1
        d -= timedelta(days=1)
    return (current, longest)
