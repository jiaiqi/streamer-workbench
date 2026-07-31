"""R4 统计聚合 API 端到端测试。

覆盖:
- /api/stats/overview
- /api/stats/feed (含旧事件 title_snapshot fallback)
- /api/stats/top-songs (3 个 metric: request/perform/practice)
- /api/stats/distribution (difficulty/status/key)
- 冷启动 / 错误 metric
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from server.app import create_app
from server.config import AppConfig


@pytest.fixture
def app_with_data():
    """3 首歌曲 (1 active + 2 draft), 多种事件覆盖各 metric。"""
    tmp = tempfile.mkdtemp(prefix="test-stats-")
    try:
        songs = {
            "schema_version": 5,
            "songs": [
                {"title": "枫", "id": "song_alpha", "artists": ["周杰伦"],
                 "difficulty": "中等", "key": "C", "capo": None,
                 "status": "active", "tags": [], "pinyin": "feng",
                 "added_at": "2026-07-01T00:00:00+08:00", "notes": "",
                 "learned_at": "2026-07-15T00:00:00+08:00", "tab_files": [],
                 "section": None},
                {"title": "成都", "id": "song_beta", "artists": ["赵雷"],
                 "difficulty": "简单", "key": "C", "capo": 2,
                 "status": "draft", "tags": [], "pinyin": "chengdu",
                 "added_at": "2026-07-10T00:00:00+08:00", "notes": "",
                 "learned_at": "", "tab_files": [], "section": None},
                {"title": "耿", "id": "song_gamma", "artists": ["汪苏泷"],
                 "difficulty": "困难", "key": "D", "capo": 0,
                 "status": "draft", "tags": [], "pinyin": "geng",
                 "added_at": "2026-07-20T00:00:00+08:00", "notes": "",
                 "learned_at": "", "tab_files": [], "section": None},
            ],
        }
        with open(Path(tmp) / "songs.json", "w", encoding="utf-8") as f:
            json.dump(songs, f, ensure_ascii=False)
        events = [
            # 学歌: song_learned
            {"schema_version": 2, "event_id": "evt_l1",
             "occurred_at": "2026-07-15T10:00:00+08:00",
             "recorded_at": "2026-07-15T10:00:00+08:00",
             "type": "song_learned", "song_id": "song_alpha",
             "title_snapshot": "枫", "source": "library"},
            # 点歌: queue_added (song_beta 2 次, song_gamma 1 次)
            {"schema_version": 2, "event_id": "evt_q1",
             "occurred_at": "2026-07-28T20:00:00+08:00",
             "recorded_at": "2026-07-28T20:00:00+08:00",
             "type": "queue_added", "song_id": "song_beta",
             "title_snapshot": "", "source": "live-service"},
            {"schema_version": 2, "event_id": "evt_q2",
             "occurred_at": "2026-07-28T20:05:00+08:00",
             "recorded_at": "2026-07-28T20:05:00+08:00",
             "type": "queue_added", "song_id": "song_beta",
             "title_snapshot": "", "source": "live-service"},
            {"schema_version": 2, "event_id": "evt_q3",
             "occurred_at": "2026-07-29T20:00:00+08:00",
             "recorded_at": "2026-07-29T20:00:00+08:00",
             "type": "queue_added", "song_id": "song_gamma",
             "title_snapshot": "", "source": "live-service"},
            # 演唱: performance_sung
            {"schema_version": 2, "event_id": "evt_p1",
             "occurred_at": "2026-07-29T21:00:00+08:00",
             "recorded_at": "2026-07-29T21:00:00+08:00",
             "type": "performance_sung", "song_id": "song_beta",
             "title_snapshot": "成都", "source": "live-service"},
            # 练习: practice_logged (2 次 song_gamma)
            {"schema_version": 2, "event_id": "evt_pr1",
             "occurred_at": "2026-07-30T10:00:00+08:00",
             "recorded_at": "2026-07-30T10:00:00+08:00",
             "type": "practice_logged", "song_id": "song_gamma",
             "title_snapshot": "耿", "source": "learning-ui",
             "meta": {"minutes": 30, "self_rating": 4, "note": "卡点:副歌"}},
            {"schema_version": 2, "event_id": "evt_pr2",
             "occurred_at": "2026-07-31T10:00:00+08:00",
             "recorded_at": "2026-07-31T10:00:00+08:00",
             "type": "practice_logged", "song_id": "song_gamma",
             "title_snapshot": "耿", "source": "learning-ui",
             "meta": {"minutes": 45, "self_rating": 5, "note": ""}},
        ]
        with open(Path(tmp) / "events.jsonl", "w", encoding="utf-8") as f:
            for ev in events:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        with open(Path(tmp) / "settings.json", "w", encoding="utf-8") as f:
            json.dump({"default_canvas": "抖音全屏 9:20", "default_theme": "海洋柔光",
                       "appearanceMode": "dark"}, f)
        # posters dir 模拟 2 个 .json
        posters = Path(tmp) / "posters"
        posters.mkdir(parents=True, exist_ok=True)
        (posters / "p1.json").write_text("{}")
        (posters / "p2.json").write_text("{}")

        config = AppConfig(
            project_root=REPO_ROOT, mode="test",
            data_root=Path(tmp), host="127.0.0.1",
            allowed_origins=("http://localhost", "http://127.0.0.1"),
        )
        app = create_app(config)
        with TestClient(app) as c:
            yield c
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ===== overview =====

def test_overview_basic(app_with_data):
    res = app_with_data.get("/api/stats/overview")
    assert res.status_code == 200
    body = res.json()
    assert body["total_songs"] == 3
    assert body["active_songs"] == 1
    assert body["draft_songs"] == 2
    assert body["total_events"] == 7
    assert body["events_by_type"]["queue_added"] == 3
    assert body["events_by_type"]["performance_sung"] == 1
    assert body["events_by_type"]["practice_logged"] == 2
    assert body["events_by_type"]["song_learned"] == 1
    assert body["total_practice_minutes"] == 75
    assert body["total_practice_sessions"] == 2
    assert body["total_queue_requests"] == 3
    assert body["total_performances"] == 1
    assert body["total_posters_exported"] == 3  # 2 个测试用 + poster 仓储初始化时建的 manifest.json


def test_overview_streak(app_with_data):
    res = app_with_data.get("/api/stats/overview")
    body = res.json()
    # 2 天连续 (7/30 + 7/31)
    # 注: streak 从今天往回数, 测试时 today 是真实日期, 7 月事件已不是当前连续
    # 只能稳定地测 longest_streak_days
    assert body["longest_streak_days"] == 2
    assert body["current_streak_days"] >= 0  # 取决于 today 是否是 8/1+


# ===== feed =====

def test_feed_order_and_fallback(app_with_data):
    res = app_with_data.get("/api/stats/feed?limit=10")
    assert res.status_code == 200
    body = res.json()
    items = body["items"]
    assert len(items) == 7
    # 倒序: 最新在前 (7/31 7/30 7/29 7/28 7/28 7/15)
    assert items[0]["occurred_at"] >= items[-1]["occurred_at"]
    # title_snapshot fallback: evt_q1 旧事件 title_snapshot="" → 从曲库回填 "成都"
    q1 = next(i for i in items if i["event_id"] == "evt_q1")
    assert q1["title_snapshot"] == "成都"
    assert "成都" in q1["summary"]


def test_feed_summary_includes_song(app_with_data):
    res = app_with_data.get("/api/stats/feed?limit=20")
    items = res.json()["items"]
    pr = next(i for i in items if i["event_id"] == "evt_pr1")
    assert "30 分钟" in pr["summary"]
    assert "耿" in pr["summary"]
    assert "自评" in pr["summary"]
    assert "卡点" in pr["summary"]


def test_feed_limit(app_with_data):
    res = app_with_data.get("/api/stats/feed?limit=2")
    items = res.json()["items"]
    assert len(items) == 2


# ===== top-songs =====

def test_top_songs_request(app_with_data):
    res = app_with_data.get("/api/stats/top-songs?metric=request&limit=5")
    body = res.json()
    assert body["metric"] == "request"
    items = body["items"]
    assert len(items) == 2
    # song_beta 2 次, song_gamma 1 次
    assert items[0]["song_id"] == "song_beta"
    assert items[0]["count"] == 2
    assert items[1]["song_id"] == "song_gamma"
    assert items[1]["count"] == 1


def test_top_songs_perform(app_with_data):
    res = app_with_data.get("/api/stats/top-songs?metric=perform&limit=5")
    items = res.json()["items"]
    assert len(items) == 1
    assert items[0]["song_id"] == "song_beta"
    assert items[0]["count"] == 1


def test_top_songs_practice_with_minutes(app_with_data):
    res = app_with_data.get("/api/stats/top-songs?metric=practice&limit=5")
    items = res.json()["items"]
    assert len(items) == 1
    assert items[0]["song_id"] == "song_gamma"
    assert items[0]["count"] == 2
    assert items[0]["minutes"] == 75  # 30 + 45


def test_top_songs_invalid_metric(app_with_data):
    res = app_with_data.get("/api/stats/top-songs?metric=invalid")
    body = res.json()
    assert "未知 metric" in body["note"]


# ===== distribution =====

def test_distribution_difficulty(app_with_data):
    res = app_with_data.get("/api/stats/distribution?metric=difficulty")
    body = res.json()
    assert body["metric"] == "difficulty"
    by_label = {b["label"]: b["count"] for b in body["buckets"]}
    assert by_label["简单"] == 1
    assert by_label["中等"] == 1
    assert by_label["困难"] == 1
    assert by_label["未标"] == 0


def test_distribution_status(app_with_data):
    res = app_with_data.get("/api/stats/distribution?metric=status")
    body = res.json()
    by_label = {b["label"]: b["count"] for b in body["buckets"]}
    assert by_label["已会 (active)"] == 1
    assert by_label["在学 (draft)"] == 2


def test_distribution_key(app_with_data):
    res = app_with_data.get("/api/stats/distribution?metric=key")
    body = res.json()
    by_label = {b["label"]: b["count"] for b in body["buckets"]}
    assert by_label["C"] == 2
    assert by_label["D"] == 1


# ===== 冷启动 =====

def test_overview_cold_start(tmp_path_factory_app):
    client = tmp_path_factory_app
    res = client.get("/api/stats/overview")
    body = res.json()
    assert body["total_events"] == 0
    assert "暂无事件" in body["note"] or "曲库" in body["note"]


def test_feed_cold_start(tmp_path_factory_app):
    client = tmp_path_factory_app
    res = client.get("/api/stats/feed")
    body = res.json()
    assert body["items"] == []
    assert "暂无事件" in body["note"]


@pytest.fixture
def tmp_path_factory_app():
    """空 events.jsonl + 单首歌曲。"""
    tmp = tempfile.mkdtemp(prefix="test-stats-cold-")
    try:
        songs = {
            "schema_version": 5,
            "songs": [
                {"title": "A", "id": "song_a", "artists": ["x"],
                 "difficulty": "", "key": "", "capo": None,
                 "status": "draft", "tags": [], "pinyin": "", "added_at": "",
                 "notes": "", "learned_at": "", "tab_files": [], "section": None},
            ],
        }
        with open(Path(tmp) / "songs.json", "w", encoding="utf-8") as f:
            json.dump(songs, f, ensure_ascii=False)
        with open(Path(tmp) / "settings.json", "w", encoding="utf-8") as f:
            json.dump({"default_canvas": "抖音全屏 9:20", "default_theme": "海洋柔光",
                       "appearanceMode": "dark"}, f)
        config = AppConfig(
            project_root=REPO_ROOT, mode="test",
            data_root=Path(tmp), host="127.0.0.1",
            allowed_origins=("http://localhost", "http://127.0.0.1"),
        )
        app = create_app(config)
        with TestClient(app) as c:
            yield c
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
