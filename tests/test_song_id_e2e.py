"""P1-A4 song_id 全链路 E2E 验证。

5 项验证（全部走 song_id 路由，不依赖 title 链）：
1. rename：PATCH /api/songs/{song_id} 改 title + 全链路
2. status：PATCH /api/songs/{song_id}/status
3. delete：DELETE /api/songs/{song_id}（30 天软删）
4. restore：POST /api/songs/{song_id}/restore
5. tab/audio access：POST/GET /api/songs/{song_id}/tabs + /api/songs/{song_id}/audio

每个用例都用 tmp_path 隔离数据，互不污染。
"""

from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from server.app import create_app  # noqa: E402
from server.config import AppConfig  # noqa: E402


# ──────────────────────────────────────────────────────────
#  共享 fixture：临时 data dir + 1 个空曲库
# ──────────────────────────────────────────────────────────

@pytest.fixture
def app_with_data():
    """临时 data dir,空曲库,settings.json 最小。"""
    tmp = tempfile.mkdtemp(prefix="test-song-id-e2e-")
    try:
        songs = {"schema_version": 5, "songs": []}
        with open(Path(tmp) / "songs.json", "w", encoding="utf-8") as f:
            json.dump(songs, f, ensure_ascii=False)
        with open(Path(tmp) / "events.jsonl", "w", encoding="utf-8") as f:
            f.write("")  # 空文件
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
    with TestClient(app) as c:
        yield c


@pytest.fixture
def created_song_id(client):
    """创建一个测试歌曲,返回 song_id;所有测试共享同一首。"""
    res = client.post("/api/songs/add", json={
        "title": "原歌名",
        "artists": ["测试歌手"],
        "key": "C",
        "capo": 0,
        "status": "draft",
    })
    assert res.status_code == 200, f"setup failed: {res.status_code} {res.text}"
    body = res.json()
    assert body["ok"] is True
    song_id = body["song"]["id"]
    assert song_id, "song_id must be non-empty"
    return song_id


# ──────────────────────────────────────────────────────────
#  1) rename
# ──────────────────────────────────────────────────────────

def test_rename_via_song_id(client, created_song_id):
    """song_id 路由 PATCH /api/songs/{id} 改 title,不需要 title 入参。"""
    res = client.patch(
        f"/api/songs/{created_song_id}",
        json={"title": "新歌名", "key": "D"},
    )
    assert res.status_code == 200, f"rename failed: {res.text}"
    body = res.json()
    assert body["ok"] is True
    assert body["song"]["title"] == "新歌名"
    assert body["song"]["key"] == "D"
    # 仍能按 id 查到
    get_res = client.get(f"/api/songs/{created_song_id}")
    assert get_res.status_code == 200
    assert get_res.json()["title"] == "新歌名"


def test_rename_not_found_404(client):
    """不存在的 song_id 返 404 而非 500。"""
    res = client.patch("/api/songs/song_does_not_exist_xyz", json={"title": "x"})
    assert res.status_code == 404, f"expected 404, got {res.status_code} {res.text}"


def test_rename_empty_id_422(client):
    """空 song_id 路径参数被 Path 校验拒绝(422)。"""
    # Pydantic 校验在 path 上,空 id 在 fastapi 路由层返 404 (路由不匹配)
    # 但超长 129 字符则进 Path 校验返 422
    long_id = "x" * 129
    res = client.patch(f"/api/songs/{long_id}", json={"title": "x"})
    assert res.status_code == 422, f"expected 422 for >128 char id, got {res.status_code}"


# ──────────────────────────────────────────────────────────
#  2) status via song_id
# ──────────────────────────────────────────────────────────

def test_status_switch_via_song_id(client, created_song_id):
    """song_id 路由 PATCH .../status:active → draft → active。"""
    # draft → active
    r1 = client.patch(
        f"/api/songs/{created_song_id}/status", json={"status": "active"})
    assert r1.status_code == 200, f"active set failed: {r1.text}"
    assert r1.json()["song"]["status"] == "active"
    assert r1.json()["active"] == 1
    # active → draft
    r2 = client.patch(
        f"/api/songs/{created_song_id}/status", json={"status": "draft"})
    assert r2.status_code == 200, f"draft set failed: {r2.text}"
    assert r2.json()["song"]["status"] == "draft"
    assert r2.json()["draft"] == 1


def test_status_invalid_400(client, created_song_id):
    """非法 status 返 400。"""
    res = client.patch(
        f"/api/songs/{created_song_id}/status", json={"status": "weird"})
    assert res.status_code == 400, f"expected 400, got {res.status_code} {res.text}"


def test_status_not_found_404(client):
    res = client.patch("/api/songs/song_ghost/status", json={"status": "active"})
    assert res.status_code == 404


# ──────────────────────────────────────────────────────────
#  3) delete via song_id (软删除 30 天)
# ──────────────────────────────────────────────────────────

def test_delete_via_song_id_soft_deletes(client, created_song_id):
    """song_id 路由 DELETE → 软删,默认 list 不应见,include_deleted=true 可见。"""
    # 先确认可见
    list1 = client.get("/api/songs/list").json()
    assert list1["total"] == 1

    # 软删
    res = client.delete(f"/api/songs/{created_song_id}")
    assert res.status_code == 200, f"delete failed: {res.text}"
    body = res.json()
    assert body["ok"] is True
    assert body["song_id"] == created_song_id
    assert body["title_snapshot"] == "原歌名"
    assert body["draft"] == 0  # 删完 0

    # 默认 list 不可见
    list2 = client.get("/api/songs/list").json()
    assert list2["total"] == 0, f"软删后仍可见: {list2}"

    # include_deleted=true 可见
    list3 = client.get("/api/songs/list?include_deleted=true").json()
    assert list3["total"] == 1
    assert list3["songs"][0]["deleted_at"] != ""


def test_delete_not_found_404(client):
    res = client.delete("/api/songs/song_ghost")
    assert res.status_code == 404


def test_delete_permanent_via_query(client, created_song_id):
    """?permanent=true 真删(不可恢复)。"""
    res = client.delete(f"/api/songs/{created_song_id}?permanent=true")
    assert res.status_code == 200
    # include_deleted=true 仍不可见(真删)
    list1 = client.get("/api/songs/list?include_deleted=true").json()
    assert list1["total"] == 0


# ──────────────────────────────────────────────────────────
#  4) restore via song_id
# ──────────────────────────────────────────────────────────

def test_restore_via_song_id(client, created_song_id):
    """软删后 song_id 路由 POST .../restore 重新可见。"""
    # 软删
    client.delete(f"/api/songs/{created_song_id}")
    list1 = client.get("/api/songs/list").json()
    assert list1["total"] == 0

    # 恢复
    res = client.post(f"/api/songs/{created_song_id}/restore")
    assert res.status_code == 200, f"restore failed: {res.text}"
    body = res.json()
    assert body["ok"] is True
    assert body["song"]["id"] == created_song_id
    assert body["song"]["deleted_at"] == ""

    # 重新可见
    list2 = client.get("/api/songs/list").json()
    assert list2["total"] == 1


def test_restore_not_found_404(client):
    res = client.post("/api/songs/song_ghost/restore")
    assert res.status_code == 404


def test_restore_keeps_data(client, created_song_id):
    """恢复后原有 title/key/artists 完整保留。"""
    # 先 PATCH 改一下
    client.patch(f"/api/songs/{created_song_id}", json={"key": "E", "capo": 2})
    client.delete(f"/api/songs/{created_song_id}")
    res = client.post(f"/api/songs/{created_song_id}/restore")
    assert res.status_code == 200
    song = res.json()["song"]
    assert song["key"] == "E"
    assert song["capo"] == 2
    assert song["title"] == "原歌名"


# ──────────────────────────────────────────────────────────
#  5) tab / audio access via song_id
# ──────────────────────────────────────────────────────────

def _make_wav_bytes(duration_ms: int = 100) -> bytes:
    """构造一段合法的 WAV 文件二进制(单声道、8kHz、16-bit PCM)。"""
    sample_rate = 8000
    n_samples = int(sample_rate * duration_ms / 1000)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * n_samples)
    return buf.getvalue()


def test_tab_upload_and_list_via_song_id(client, created_song_id):
    """song_id 路由 POST .../tabs 上传 + GET .../tabs 列出。"""
    # 上传
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32  # 假 PNG bytes
    res = client.post(
        f"/api/songs/{created_song_id}/tabs",
        files={"file": ("chord.png", fake_png, "image/png")},
    )
    assert res.status_code == 200, f"upload failed: {res.text}"
    body = res.json()
    assert body["ok"] is True
    assert body["song_id"] == created_song_id
    # tab_files 返的是相对路径列表(tabs/{song_id}/chord.png)
    assert any(p.endswith("chord.png") for p in body["tab_files"]), \
        f"chord.png not in {body['tab_files']}"

    # 列出
    list_res = client.get(f"/api/songs/{created_song_id}/tabs")
    assert list_res.status_code == 200
    list_body = list_res.json()
    assert list_body["song_id"] == created_song_id
    assert any(p.endswith("chord.png") for p in list_body["tab_files"]), \
        f"chord.png not in {list_body['tab_files']}"


def test_audio_upload_via_song_id(client, created_song_id):
    """song_id 路由 POST .../audio 上传 WAV 音频 + GET 列出。"""
    wav_bytes = _make_wav_bytes(duration_ms=100)
    res = client.post(
        f"/api/songs/{created_song_id}/audio",
        params={"role": "vocal"},
        files={"file": ("vocal.wav", wav_bytes, "audio/wav")},
    )
    assert res.status_code == 200, f"audio upload failed: {res.text}"
    body = res.json()
    assert body["ok"] is True
    assert body["song_id"] == created_song_id
    assert body["role"] == "vocal"
    assert body["filename"].endswith(".wav")
    assert body["path"].endswith(".wav")

    # 列出
    list_res = client.get(f"/api/songs/{created_song_id}/audio/list")
    assert list_res.status_code == 200, f"audio list failed: {list_res.text}"
    list_body = list_res.json()
    assert list_body["song_id"] == created_song_id
    roles = [f["role"] for f in list_body["items"]]
    assert "vocal" in roles


# ──────────────────────────────────────────────────────────
#  6) 全链路收口(组合场景)
# ──────────────────────────────────────────────────────────

def test_full_lifecycle_via_song_id(client):
    """组合:创建 → rename → status → 软删 → 恢复 → tab 上传,全走 song_id。"""
    # 1. 创建
    create_res = client.post("/api/songs/add", json={
        "title": "链路测试", "artists": ["Singer"], "status": "draft",
    })
    assert create_res.status_code == 200
    song_id = create_res.json()["song"]["id"]

    # 2. rename
    r1 = client.patch(f"/api/songs/{song_id}", json={"title": "链路测试v2", "key": "G"})
    assert r1.status_code == 200
    assert r1.json()["song"]["title"] == "链路测试v2"

    # 3. status 切换
    r2 = client.patch(f"/api/songs/{song_id}/status", json={"status": "active"})
    assert r2.status_code == 200
    assert r2.json()["song"]["status"] == "active"

    # 4. tab 上传
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    r3 = client.post(
        f"/api/songs/{song_id}/tabs",
        files={"file": ("tab.png", fake_png, "image/png")},
    )
    assert r3.status_code == 200
    assert any(p.endswith("tab.png") for p in r3.json()["tab_files"])

    # 5. 软删
    r4 = client.delete(f"/api/songs/{song_id}")
    assert r4.status_code == 200
    assert r4.json()["song_id"] == song_id

    # 6. list 默认不可见
    list1 = client.get("/api/songs/list").json()
    assert list1["total"] == 0

    # 7. 恢复
    r5 = client.post(f"/api/songs/{song_id}/restore")
    assert r5.status_code == 200
    assert r5.json()["song"]["title"] == "链路测试v2"
    assert r5.json()["song"]["status"] == "active"
    # tab_files 仍然在(因为软删不动附件)
    assert any(p.endswith("tab.png") for p in r5.json()["song"]["tab_files"])

    # 8. 重新可见
    list2 = client.get("/api/songs/list").json()
    assert list2["total"] == 1
    assert list2["active"] == 1


# ──────────────────────────────────────────────────────────
#  7) legacy title 路由仍可用 + Deprecation header
# ──────────────────────────────────────────────────────────

def test_legacy_title_status_routes_still_work_with_deprecation(client, created_song_id):
    """旧 title 路由仍能用,但响应带 Deprecation + Sunset header。"""
    # 用 song_id 创建的歌,取 title 调旧路由
    get_res = client.get(f"/api/songs/{created_song_id}")
    title = get_res.json()["title"]
    res = client.post(
        "/api/songs/status",
        json={"title": title, "status": "active"},
    )
    assert res.status_code == 200, f"legacy route broken: {res.text}"
    assert res.headers.get("deprecation") == "true"
    assert "Sunset" in res.headers
    assert res.json()["ok"] is True


def test_legacy_title_delete_routes_still_work_with_deprecation(client, created_song_id):
    """旧 title delete 路由仍能用,带 deprecation header。"""
    get_res = client.get(f"/api/songs/{created_song_id}")
    title = get_res.json()["title"]
    res = client.post("/api/songs/delete", json={"title": title})
    assert res.status_code == 200, f"legacy delete broken: {res.text}"
    assert res.headers.get("deprecation") == "true"
    assert "Sunset" in res.headers
