"""R3 学歌发现 API 端到端测试。

覆盖:
- /api/discovery/recent-learned (空 / 有数据)
- /api/discovery/request-hot (按 queue_added + performance_sung 加权)
- /api/discovery/recommend (综合学习间隔 + 点歌热度 + 难度)
- 空 events (冷启动)
- limit 参数
"""
from __future__ import annotations

import json
import os
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
    """临时 data dir: 1 active + 1 draft 歌曲 + 几个 events。"""
    tmp = tempfile.mkdtemp(prefix="test-discovery-")
    try:
        # songs.json: 1 active (song_learned 有), 1 draft (没标记)
        songs = {
            "schema_version": 5,
            "songs": [
                {
                    "title": "枫",
                    "id": "song_alpha",
                    "artists": ["周杰伦"],
                    "difficulty": "中等",
                    "key": "C",
                    "capo": None,
                    "status": "active",
                    "tags": [],
                    "pinyin": "feng",
                    "added_at": "2026-07-01T00:00:00+08:00",
                    "notes": "",
                    "learned_at": "2026-07-15T00:00:00+08:00",
                    "tab_files": [],
                    "section": None,
                },
                {
                    "title": "成都",
                    "id": "song_beta",
                    "artists": ["赵雷"],
                    "difficulty": "简单",
                    "key": "C",
                    "capo": 2,
                    "status": "draft",
                    "tags": [],
                    "pinyin": "chengdu",
                    "added_at": "2026-07-10T00:00:00+08:00",
                    "notes": "",
                    "learned_at": "",
                    "tab_files": [],
                    "section": None,
                },
                {
                    "title": "耿",
                    "id": "song_gamma",
                    "artists": ["汪苏泷"],
                    "difficulty": "困难",
                    "key": "D",
                    "capo": 0,
                    "status": "draft",
                    "tags": [],
                    "pinyin": "geng",
                    "added_at": "2026-07-20T00:00:00+08:00",
                    "notes": "",
                    "learned_at": "",
                    "tab_files": [],
                    "section": None,
                },
            ],
        }
        with open(Path(tmp) / "songs.json", "w", encoding="utf-8") as f:
            json.dump(songs, f, ensure_ascii=False)

        # events.jsonl: song_learned + queue_added + performance_sung + practice_logged
        events = [
            # song_alpha 学会过
            {
                "schema_version": 2, "event_id": "evt_l1",
                "occurred_at": "2026-07-15T10:00:00+08:00",
                "recorded_at": "2026-07-15T10:00:00+08:00",
                "type": "song_learned", "song_id": "song_alpha",
                "title_snapshot": "枫", "source": "library",
            },
            # song_beta 最近被点过
            {
                "schema_version": 2, "event_id": "evt_q1",
                "occurred_at": "2026-07-28T20:00:00+08:00",
                "recorded_at": "2026-07-28T20:00:00+08:00",
                "type": "queue_added", "song_id": "song_beta",
                "title_snapshot": "成都", "source": "live-service",
            },
            {
                "schema_version": 2, "event_id": "evt_q2",
                "occurred_at": "2026-07-28T20:05:00+08:00",
                "recorded_at": "2026-07-28T20:05:00+08:00",
                "type": "queue_added", "song_id": "song_beta",
                "title_snapshot": "成都", "source": "live-service",
            },
            # song_gamma 被演唱
            {
                "schema_version": 2, "event_id": "evt_p1",
                "occurred_at": "2026-07-29T21:00:00+08:00",
                "recorded_at": "2026-07-29T21:00:00+08:00",
                "type": "performance_sung", "song_id": "song_gamma",
                "title_snapshot": "耿", "source": "live-service",
            },
            # song_gamma 30 天前练习
            {
                "schema_version": 2, "event_id": "evt_pr1",
                "occurred_at": "2026-07-01T10:00:00+08:00",
                "recorded_at": "2026-07-01T10:00:00+08:00",
                "type": "practice_logged", "song_id": "song_gamma",
                "title_snapshot": "耿", "source": "learning-ui",
                "meta": {"minutes": 30, "self_rating": 4, "note": ""},
            },
        ]
        with open(Path(tmp) / "events.jsonl", "w", encoding="utf-8") as f:
            for ev in events:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")

        # settings.json (最小)
        with open(Path(tmp) / "settings.json", "w", encoding="utf-8") as f:
            json.dump({
                "default_canvas": "抖音全屏 9:20",
                "default_theme": "海洋柔光",
                "appearanceMode": "dark",
            }, f)

        config = AppConfig(
            project_root=REPO_ROOT,
            mode="test",
            data_root=Path(tmp),
            host="127.0.0.1",
            allowed_origins=("http://localhost", "http://127.0.0.1"),
        )
        app = create_app(config)
        yield app, tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def client(app_with_data):
    app, _ = app_with_data
    # TestClient 需要 lifespan 上下文才能初始化 app.state.context
    with TestClient(app) as c:
        yield c


# ===== recent_learned =====

def test_recent_learned_returns_learned_song(client):
    res = client.get("/api/discovery/recent-learned?limit=10")
    assert res.status_code == 200
    body = res.json()
    assert "items" in body
    assert "note" in body
    # 1 个 song_learned 事件 → 1 项
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["song_id"] == "song_alpha"
    assert item["title"] == "枫"
    assert item["artist"] == "周杰伦"
    assert item["difficulty"] == "中等"
    assert item["last_learned_at"].startswith("2026-07-15")


def test_recent_learned_respects_limit(client):
    res = client.get("/api/discovery/recent-learned?limit=0")
    assert res.status_code == 200
    body = res.json()
    assert len(body["items"]) == 0


# ===== request_hot =====

def test_request_hot_aggregates_queue_and_perform(client):
    res = client.get("/api/discovery/request-hot?limit=10&since_days=90")
    assert res.status_code == 200
    body = res.json()
    items = body["items"]
    # song_beta: queue 2, perform 0, 热度 2
    # song_gamma: queue 0, perform 1, 热度 2
    # 二者平手, 按 dict 顺序 (set 无序, 看 count)
    assert len(items) == 2
    by_id = {i["song_id"]: i for i in items}
    assert by_id["song_beta"]["request_count"] == 2
    assert by_id["song_beta"]["perform_count"] == 0
    assert by_id["song_gamma"]["request_count"] == 0
    assert by_id["song_gamma"]["perform_count"] == 1
    # 全部 reason 字段非空
    for i in items:
        assert i["reason"]


def test_request_hot_since_window(client):
    # 一年窗口应该全包含
    res = client.get("/api/discovery/request-hot?since_days=365")
    body = res.json()
    assert len(body["items"]) == 2


# ===== recommend =====

def test_recommend_returns_active_songs(client):
    res = client.get("/api/discovery/recommend?limit=10")
    assert res.status_code == 200
    body = res.json()
    items = body["items"]
    # song_alpha 是已会且没最近练习 → 跳过
    # song_beta: 未练习 + 被点 + 难度简单 (无加成) → 入选
    # song_gamma: 30 天前练习 + 演唱过 + 困难 (加成 0.2) → 入选
    # 顺序: 间隔高+点歌的 song_beta 应该排前
    ids = [i["song_id"] for i in items]
    assert "song_alpha" not in ids  # 已会跳过
    assert "song_beta" in ids
    assert "song_gamma" in ids
    # 全部有 reason
    for i in items:
        assert i["reason"]


def test_recommend_respects_limit(client):
    res = client.get("/api/discovery/recommend?limit=1")
    body = res.json()
    assert len(body["items"]) == 1


# ===== 冷启动 =====

def test_empty_events_returns_note(tmp_path_factory_app):
    """events.jsonl 不存在时, recent_learned/request_hot 返回 note 不报错。"""
    pass  # 见下


@pytest.fixture
def tmp_path_factory_app():
    """events.jsonl 不存在, 只有 songs.json。"""
    tmp = tempfile.mkdtemp(prefix="test-cold-start-")
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
        # events.jsonl 不创建
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


def test_cold_start_no_events(tmp_path_factory_app):
    client = tmp_path_factory_app
    res1 = client.get("/api/discovery/recent-learned")
    assert res1.status_code == 200
    body1 = res1.json()
    assert body1["items"] == []
    assert "尚未" in body1["note"] or "无" in body1["note"]

    res2 = client.get("/api/discovery/request-hot")
    assert res2.status_code == 200
    body2 = res2.json()
    assert body2["items"] == []

    # recommend 在冷启动时仍有 1 首歌 (song_a, 未练习/未标记)
    res3 = client.get("/api/discovery/recommend")
    body3 = res3.json()
    assert "items" in body3
