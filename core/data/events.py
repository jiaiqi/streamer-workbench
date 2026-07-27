"""事件日志层（追加式 JSONL）。

一切带时间维度的历史（曲库变更/学会/练习打卡/直播点歌/海报导出）都写成
data/events.jsonl 里的一行一个 JSON 对象：

    {"ts": "2026-07-27T21:03:11", "type": "song_learned", "title": "凄美地", "meta": {...}}

设计决策（design/roadmap-data-stats.md 第 3 节）：
  - songs.json 仍是当前状态的唯一真相；本文件只追加、不改写，专记历史；
  - append 模式 open-write-close，一行一事件，崩溃截断最多坏最后一行；
  - 统计只算不存：需要聚合时由 server 调 iter_events() 现算；
  - 撤退路线：事件量破万后可整体导入 SQLite，schema 不变。
"""
import json
import os
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


def append_event(path: str, type: str, title: Optional[str] = None,
                 meta: Optional[dict] = None) -> dict:
    """向 events.jsonl 追加一个事件，返回写入的事件对象。

    type 必须在 EVENT_TYPES 白名单内（防手滑写出无法统计的类型名）。
    """
    if type not in EVENT_TYPES:
        raise ValueError(f"未知事件类型：{type}（白名单见 EVENT_TYPES）")
    event = {"ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), "type": type}
    if title is not None:
        event["title"] = title
    if meta:
        event["meta"] = meta
    os.makedirs(os.path.dirname(path), exist_ok=True)
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
            ts = event.get("ts", "")
            if since and ts < since:
                continue
            if until and ts > until:
                continue
            yield event


def tail(path: str, n: int = 50, type: Optional[str] = None) -> list:
    """最近 n 条事件（倒序，最新在前）。更新记录 feed 用。"""
    events = list(iter_events(path, type=type))
    return events[::-1][:n]
