"""单元测试：theme loader / Song 模型 / 布局 / 分组规则。

覆盖设计结论 §9.1 要求的主题校验异常路径、Song 模型生命周期、
分组规则（section 标记 + 字数回退）。
"""
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.themes.loader import load_themes, load_theme
from core.themes.model import Theme
from core.style import Style
from core.data.songs import Song, SongLibrary, build_default_library
from core.data.events import append_event, iter_events, tail as events_tail
from core.layouts import get_layout, list_layouts

THEMES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "themes")


# ═══════ Theme Loader ═══════

def test_load_themes_all_7():
    themes = load_themes(THEMES_DIR)
    assert len(themes) == 7
    assert "海洋柔光" in themes
    assert "青提气泡" in themes

def test_theme_styles_have_5_roles():
    themes = load_themes(THEMES_DIR)
    for name, t in themes.items():
        for page in (1, 2):
            s = t.styles[page]
            assert s.text is not None
            assert s.label is not None
            assert s.pill is not None
            assert s.line is not None
            assert s.mist is not None

def test_theme_backgrounds_exist():
    themes = load_themes(THEMES_DIR)
    for name, t in themes.items():
        for page in (1, 2):
            path = t.background_path(page)
            assert os.path.isfile(path), f"{name} p{page}: {path}"

def test_theme_json_format():
    themes = load_themes(THEMES_DIR)
    for name, t in themes.items():
        assert t.name
        assert t.output_prefix
        assert isinstance(t.backgrounds, dict)
        assert "1" in t.backgrounds
        assert "2" in t.backgrounds
        assert isinstance(t.watermark_fix, bool)

def test_loader_missing_field_detected():
    import json, tempfile
    bad = {"name": "x", "output_prefix": "x", "backgrounds": {"1": "x.png"}}
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(bad, f)
    p = f.name
    f.close()
    try:
        load_theme(p)
        assert False, "Should raise ValueError"
    except (ValueError, KeyError):
        pass
    finally:
        os.unlink(p)


# ═══════ Song Model ═══════

def test_song_default_status_active():
    s = Song(title="x")
    assert s.status == "active"

def test_library_active():
    lib = SongLibrary([
        Song(title="a", status="active"),
        Song(title="b", status="draft"),
        Song(title="c", status="active"),
    ])
    a = lib.active()
    assert len(a) == 2
    assert {s.title for s in a} == {"a", "c"}

def test_library_mastered_compat():
    lib = SongLibrary([
        Song(title="a", status="active"),
        Song(title="b", status="draft"),
    ])
    assert len(lib.mastered()) == len(lib.active())

def test_library_add_duplicate():
    lib = SongLibrary([Song(title="a")])
    assert lib.add(Song(title="a")) is False
    assert lib.add(Song(title="b")) is True

def test_library_add_duplicate_id():
    first = Song(title="a")
    lib = SongLibrary([first])
    assert lib.add(Song(title="b", id=first.id)) is False

def test_library_get_by_id_survives_rename():
    song = Song(title="a")
    lib = SongLibrary([song])
    assert lib.update("a", {"title": "renamed"}) is True
    assert lib.get_by_id(song.id).title == "renamed"

def test_library_id_operations_survive_rename():
    song = Song(title="a", status="draft")
    lib = SongLibrary([song, Song(title="b")])
    assert lib.update_by_id(song.id, {"title": "renamed", "key": "G"}) is True
    assert lib.get_by_id(song.id).title == "renamed"
    assert lib.get_by_id(song.id).key == "G"
    assert lib.mark_active_by_id(song.id) is True
    assert lib.get_by_id(song.id).status == "active"
    assert lib.mark_draft_by_id(song.id) is True
    assert lib.get_by_id(song.id).status == "draft"
    assert lib.remove_by_id(song.id) is True
    assert lib.get_by_id(song.id) is None

def test_library_id_rename_rejects_duplicate_without_mutation():
    song = Song(title="a")
    lib = SongLibrary([song, Song(title="b")])
    try:
        lib.update_by_id(song.id, {"title": "b", "key": "G"})
        assert False, "按 ID 改名撞车应抛 ValueError"
    except ValueError:
        pass
    assert lib.get_by_id(song.id).title == "a"
    assert lib.get_by_id(song.id).key == ""

def test_mark_active():
    lib = SongLibrary([Song(title="a", status="draft"), Song(title="b", status="active")])
    assert lib.mark_active("a") is True
    assert lib.mark_active("x") is False
    assert [s.status for s in lib.songs] == ["active", "active"]

def test_mark_draft():
    lib = SongLibrary([Song(title="a", status="active"), Song(title="b", status="draft")])
    assert lib.mark_draft("a") is True
    assert lib.mark_draft("x") is False
    assert [s.status for s in lib.songs] == ["draft", "draft"]

def test_update():
    lib = SongLibrary([Song(title="a"), Song(title="b")])
    assert lib.update("a", {"key": "G", "capo": 2, "tags": ["小甜歌"]}) is True
    s = lib.get("a")
    assert s.key == "G" and s.capo == 2 and s.tags == ["小甜歌"]
    assert lib.update("x", {"key": "C"}) is False

def test_update_rename_dedupe():
    lib = SongLibrary([Song(title="a"), Song(title="b")])
    assert lib.update("a", {"title": "c"}) is True
    assert lib.get("c") is not None and lib.get("a") is None
    try:
        lib.update("b", {"title": "c"})
        assert False, "改名撞车应抛 ValueError"
    except ValueError:
        pass

def test_remove():
    lib = SongLibrary([Song(title="a"), Song(title="b")])
    assert lib.remove("a") is True
    assert lib.remove("x") is False
    assert [s.title for s in lib.songs] == ["b"]

def test_migration_v1_to_v2_capo():
    data = {"version": 1, "songs": [
        {"title": "a", "capo": 0}, {"title": "b", "capo": 3}]}
    out = SongLibrary._migrate_v1_to_v2(data)
    assert out["songs"][0]["capo"] is None
    assert out["songs"][1]["capo"] == 3

def test_migration_v2_to_v3_pinyin():
    data = {"version": 2, "songs": [
        {"title": "知足", "pinyin": ""},          # 空 → 回填
        {"title": "枫", "pinyin": "custom"},      # 手工非空 → 保留
        {"title": "", "pinyin": ""}]}             # 无标题 → 不炸
    out = SongLibrary._migrate_v2_to_v3(data)
    assert out["songs"][0]["pinyin"] == "zz"
    assert out["songs"][1]["pinyin"] == "custom"
    assert out["songs"][2]["pinyin"] == ""

def test_migration_chain_v1_to_v3():
    data = {"version": 1, "songs": [{"title": "知足", "capo": 0, "pinyin": ""}]}
    out = SongLibrary._migrate(data)
    assert out["songs"][0]["capo"] is None
    assert out["songs"][0]["pinyin"] == "zz"

def test_migration_v3_to_v4_fields():
    data = {"version": 3, "songs": [
        {"title": "a"},                                  # 无新字段 → 补默认
        {"title": "b", "learned_at": "2026-07-01",       # 已有值 → 保留
         "tab_files": ["tabs/b/主歌.png"]}]}
    out = SongLibrary._migrate(data)
    assert out["songs"][0]["learned_at"] == ""
    assert out["songs"][0]["tab_files"] == []
    assert out["songs"][1]["learned_at"] == "2026-07-01"
    assert out["songs"][1]["tab_files"] == ["tabs/b/主歌.png"]

def test_migration_chain_v1_to_v5():
    data = {"version": 1, "songs": [{"title": "知足", "capo": 0, "pinyin": ""}]}
    out = SongLibrary._migrate(data)
    s = out["songs"][0]
    assert s["capo"] is None and s["pinyin"] == "zz"
    assert s["learned_at"] == "" and s["tab_files"] == []
    assert s["id"].startswith("song_")
    assert out["version"] == 5

def test_migration_v4_to_v5_is_deterministic():
    source = {"version": 4, "songs": [{"title": "知足"}, {"title": "枫"}]}
    first = SongLibrary._migrate(copy.deepcopy(source))
    second = SongLibrary._migrate(copy.deepcopy(source))
    assert [s["id"] for s in first["songs"]] == [s["id"] for s in second["songs"]]
    assert len({s["id"] for s in first["songs"]}) == 2

def test_migration_v5_rejects_invalid_identity():
    cases = [
        {"version": 5, "songs": [{"id": "", "title": "a"}]},
        {"version": 5, "songs": [{"id": "same", "title": "a"},
                                   {"id": "same", "title": "b"}]},
        {"version": 5, "songs": [{"id": "one", "title": "a"},
                                   {"id": "two", "title": "a"}]},
    ]
    for data in cases:
        try:
            SongLibrary._migrate(data)
            assert False, "无效 v5 身份应被拒绝"
        except ValueError:
            pass

def test_save_load_roundtrip_v5():
    import json, tempfile
    with tempfile.TemporaryDirectory() as d:
        lib = SongLibrary([Song(title="知足", learned_at="2026-07-27",
                                tab_files=["tabs/知足/chorus.png"])])
        p = os.path.join(d, "songs.json")
        lib.save(p)
        with open(p, encoding="utf-8") as f:
            assert json.load(f)["version"] == 5
        loaded = SongLibrary.load_from_json(p)
        s = loaded.get("知足")
        assert s.id == lib.get("知足").id
        assert s.learned_at == "2026-07-27"
        assert s.tab_files == ["tabs/知足/chorus.png"]

def test_first_v5_save_backs_up_v4_file():
    import json, tempfile
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "songs.json")
        backups = os.path.join(d, "backups")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"version": 4, "songs": [{"title": "知足"}]}, f,
                      ensure_ascii=False)
        lib = SongLibrary.load_from_json(path)
        lib.save(path, backup_dir=backups)
        backup_files = os.listdir(backups)
        assert len(backup_files) == 1
        with open(os.path.join(backups, backup_files[0]), encoding="utf-8") as f:
            assert json.load(f)["version"] == 4
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["version"] == 5
        assert saved["songs"][0]["id"] == lib.songs[0].id


# ═══════ 事件日志（core/data/events.py）═══════
# 注：tmp 目录用 tempfile 手写而不用 pytest tmp_path fixture，
# 因为项目兜底 runner（python tests/test_unit.py 直跑）不支持 fixture。

def _tmpevents():
    """返回 (tmpdir 句柄, events.jsonl 路径)。调用方需持有句柄防回收。"""
    import tempfile
    d = tempfile.TemporaryDirectory()
    return d, os.path.join(d.name, "events.jsonl")

def test_event_append_and_read():
    d, p = _tmpevents()
    e1 = append_event(p, "song_added", song_id="song_1", title_snapshot="知足",
                      meta={"status": "draft"}, source="test")
    assert e1["schema_version"] == 2
    assert e1["type"] == "song_added" and e1["song_id"] == "song_1"
    assert e1["title_snapshot"] == "知足" and e1["source"] == "test"
    assert e1["event_id"].startswith("evt_")
    assert "+" in e1["occurred_at"] and "+" in e1["recorded_at"]
    append_event(p, "song_learned", title="知足")  # v1 参数名仍可调用，写出 v2
    events = list(iter_events(p))
    assert len(events) == 2
    assert events[1]["type"] == "song_learned"
    assert events[1]["title_snapshot"] == "知足"
    d.cleanup()

def test_event_type_whitelist():
    d, p = _tmpevents()
    try:
        append_event(p, "song_lerned")  # 拼错的类型名必须被拦截
        assert False, "应抛 ValueError"
    except ValueError:
        pass
    d.cleanup()

def test_event_iter_filters():
    d, p = _tmpevents()
    append_event(p, "queue_added", title="知足")
    append_event(p, "song_sung", title="知足")
    append_event(p, "song_sung", title="成都")
    assert len(list(iter_events(p, type="song_sung"))) == 2
    # since/until 前缀比较（ts 固定 ISO 格式）
    today = events_tail(p, n=1)[0]["occurred_at"][:10]
    assert len(list(iter_events(p, since=today))) == 3
    assert len(list(iter_events(p, until="2020-01-01"))) == 0
    d.cleanup()

def test_event_missing_file_and_bad_line():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "nope", "events.jsonl")
        assert list(iter_events(p)) == []            # 文件不存在 → 空迭代
        os.makedirs(os.path.dirname(p))
        with open(p, "w", encoding="utf-8") as f:
            f.write('{"ts":"2026-07-27T10:00:00","type":"song_added","title":"a"}\n')
            f.write("{坏行（崩溃截断）\n")
        events = list(iter_events(p))
        assert len(events) == 1 and events[0]["title"] == "a"

def test_event_tail_order():
    d, p = _tmpevents()
    for t in ["歌一", "歌二", "歌三"]:
        append_event(p, "song_added", title=t)
    recent = events_tail(p, n=2)
    assert [e["title_snapshot"] for e in recent] == ["歌三", "歌二"]  # 最新在前 + limit 生效
    d.cleanup()

def test_event_custom_ts():
    """客户端补报离线事件时可传原始时刻（S2 QuickView 双写用）。"""
    d, p = _tmpevents()
    e = append_event(p, "song_sung", title="知足", ts="2026-07-20T22:30:05")
    assert e["occurred_at"].startswith("2026-07-20T22:30:05")
    assert e["recorded_at"] != e["occurred_at"]
    d.cleanup()

def test_event_idempotent_report():
    d, p = _tmpevents()
    kwargs = {"event_id": "evt_fixed", "song_id": "song_1",
              "title_snapshot": "知足", "occurred_at": "2026-07-20T22:30:05",
              "source": "quick-view"}
    first = append_event(p, "song_sung", **kwargs)
    second = append_event(p, "song_sung", **kwargs)
    assert first == second
    assert len(list(iter_events(p))) == 1
    try:
        append_event(p, "queue_added", **kwargs)
        assert False, "同 event_id 的不同事件应被拒绝"
    except ValueError:
        pass
    d.cleanup()

def test_event_v1_read_compatibility():
    import json
    d, p = _tmpevents()
    with open(p, "w", encoding="utf-8") as f:
        f.write(json.dumps({"ts": "2026-07-01T10:00:00", "type": "song_added",
                            "title": "旧事件"}, ensure_ascii=False) + "\n")
    events = list(iter_events(p, since="2026-07-01"))
    assert len(events) == 1 and events[0]["title"] == "旧事件"
    d.cleanup()


# ═══════ R0.5 Song ID 服务端主链路 ═══════

def _request_for_library(library):
    from types import SimpleNamespace
    import tempfile
    import copy
    from server.repositories.events import FileEventStore
    from server.ports.repositories import StoredSnapshot

    class MemorySongRepository:
        def __init__(self, value):
            self.value = value
            self.revision = "memory-1"

        def load(self):
            return StoredSnapshot(self.value, self.revision)

        def save(self, value, *, expected_revision):
            self.value = value
            self.revision = "memory-2"
            return self.load()

    root = tempfile.mkdtemp(prefix="streamer-workbench-test-")
    paths = SimpleNamespace(
        songs_json=os.path.join(root, "songs.json"),
        events_jsonl=os.path.join(root, "events.jsonl"),
        tabs_dir=os.path.join(root, "tabs"),
        backups_dir=os.path.join(root, "backups"),
        settings_json=os.path.join(root, "settings.json"),
        presets_dir=os.path.join(root, "presets"),
    )
    context = SimpleNamespace(song_repository=MemorySongRepository(library),
                              event_store=FileEventStore(paths.events_jsonl),
                              settings_repository={"backup_count": 20},
                              preset_repository=paths.presets_dir,
                              paths=paths)
    state = SimpleNamespace(library=library, settings=context.settings_repository,
                            context=context)
    return SimpleNamespace(app=SimpleNamespace(state=state))

def test_song_id_api_rename_keeps_identity_and_event_link():
    import server.routers.songs as songs_router
    song = Song(title="旧歌名", id="song_stable")
    library = SongLibrary([song])
    request = _request_for_library(library)
    saved = []
    events = []
    old_save = songs_router._save_library
    old_append = songs_router._append_event
    old_events_path = songs_router._events_path
    try:
        songs_router._save_library = lambda context, library: saved.append(library)
        songs_router._events_path = lambda context: "unused-events.jsonl"
        songs_router._append_event = lambda context, event_type, **kwargs: events.append(
            {"type": event_type, **kwargs})
        result = songs_router.api_song_update_by_id(
            request, "song_stable", {"title": "新歌名", "key": "G"})
    finally:
        songs_router._save_library = old_save
        songs_router._append_event = old_append
        songs_router._events_path = old_events_path
    assert result["ok"] is True
    assert result["song"]["id"] == "song_stable"
    assert result["song"]["title"] == "新歌名"
    assert library.get_by_id("song_stable").title == "新歌名"
    assert len(saved) == 1
    assert events[0]["song_id"] == "song_stable"
    assert events[0]["title_snapshot"] == "新歌名"

def test_song_id_api_rename_conflict_does_not_save():
    import server.routers.songs as songs_router
    first = Song(title="第一首", id="song_first")
    library = SongLibrary([first, Song(title="第二首", id="song_second")])
    request = _request_for_library(library)
    saves = []
    old_save = songs_router._save_library
    try:
        songs_router._save_library = lambda context, library: saves.append(library)
        response = songs_router.api_song_update_by_id(
            request, "song_first", {"title": "第二首"})
    finally:
        songs_router._save_library = old_save
    assert response.status_code == 409
    assert library.get_by_id("song_first").title == "第一首"
    assert saves == []

def test_song_id_api_delete_preserves_snapshot_in_event():
    import server.routers.songs as songs_router
    song = Song(title="待删除", id="song_delete")
    library = SongLibrary([song])
    request = _request_for_library(library)
    events = []
    old_save = songs_router._save_library
    old_append = songs_router._append_event
    old_events_path = songs_router._events_path
    try:
        songs_router._save_library = lambda context, library: None
        songs_router._events_path = lambda context: "unused-events.jsonl"
        songs_router._append_event = lambda context, event_type, **kwargs: events.append(
            {"type": event_type, **kwargs})
        result = songs_router.api_song_delete_by_id(request, "song_delete")
    finally:
        songs_router._save_library = old_save
        songs_router._append_event = old_append
        songs_router._events_path = old_events_path
    assert result["song_id"] == "song_delete"
    assert result["title_snapshot"] == "待删除"
    assert library.get_by_id("song_delete") is None
    assert events == [{"type": "song_deleted", "song_id": "song_delete",
                       "title_snapshot": "待删除", "source": "songs-api"}]

def test_event_report_rejects_unknown_explicit_song_id():
    import server.routers.events as events_router
    request = _request_for_library(SongLibrary([Song(title="知足", id="song_known")]))
    response = events_router.api_events_report(request, {
        "type": "song_sung", "song_id": "song_missing", "title_snapshot": "知足",
    })
    assert response.status_code == 404

def test_event_report_explicit_song_id_requires_complete_v2_envelope():
    import server.routers.events as events_router
    request = _request_for_library(SongLibrary([Song(title="知足", id="song_known")]))
    response = events_router.api_events_report(request, {
        "type": "song_sung", "song_id": "song_known", "title_snapshot": "知足",
    })
    assert response.status_code == 400
    assert b"event_id" in response.body
    assert b"occurred_at" in response.body
    assert b"source" in response.body

def test_event_report_complete_v2_refreshes_title_and_keeps_client_identity():
    import server.routers.events as events_router
    request = _request_for_library(SongLibrary([Song(title="新歌名", id="song_known")]))
    result = events_router.api_events_report(request, {
            "type": "song_sung",
            "event_id": "evt_client_fixed",
            "song_id": "song_known",
            "title_snapshot": "旧歌名",
            "occurred_at": "2026-07-28T20:00:00+08:00",
            "source": "quick-view",
    })
    assert result["ok"] is True
    assert result["event"]["event_id"] == "evt_client_fixed"
    assert result["event"]["song_id"] == "song_known"
    assert result["event"]["title_snapshot"] == "新歌名"
    assert result["event"]["occurred_at"] == "2026-07-28T20:00:00+08:00"

def test_event_report_legacy_title_must_resolve_to_song_id():
    import server.routers.events as events_router
    request = _request_for_library(SongLibrary([]))
    response = events_router.api_events_report(request, {
        "type": "queue_added", "title": "不存在的歌",
    })
    assert response.status_code == 400

def test_song_router_registers_id_primary_and_title_compat_routes():
    from server.routers.songs import router as songs_router
    routes = {(route.path, frozenset(route.methods or set())) for route in songs_router.routes}
    assert ("/api/songs/{song_id}", frozenset({"GET"})) in routes
    assert ("/api/songs/{song_id}", frozenset({"PATCH"})) in routes
    assert ("/api/songs/{song_id}", frozenset({"DELETE"})) in routes
    assert ("/api/songs/{song_id}/status", frozenset({"PATCH"})) in routes
    assert ("/api/songs/update", frozenset({"POST"})) in routes
    assert ("/api/songs/delete", frozenset({"POST"})) in routes
    assert ("/api/songs/status", frozenset({"POST"})) in routes

def test_song_title_compat_rename_conflict_matches_id_api():
    import server.routers.songs as songs_router
    library = SongLibrary([
        Song(title="第一首", id="song_first"),
        Song(title="第二首", id="song_second"),
    ])
    request = _request_for_library(library)
    saves = []
    old_save = songs_router._save_library
    try:
        songs_router._save_library = lambda context, library: saves.append(library)
        response = songs_router.api_songs_update(
            request, {"title": "第一首", "fields": {"title": "第二首"}})
    finally:
        songs_router._save_library = old_save
    assert response.status_code == 409
    assert library.get_by_id("song_first").title == "第一首"
    assert saves == []


# ═══════ 曲谱存储（core/data/tabs.py）═══════
from core.data import tabs as tabs_store

def test_tabs_sanitize_name():
    assert tabs_store.sanitize_name("../etc/passwd") == "_etc_passwd"  # "/" → "_"，去开头点
    assert tabs_store.sanitize_name("..hidden") == "hidden"
    assert tabs_store.sanitize_name("a/b\\c") == "a_b_c"
    assert tabs_store.sanitize_name("") == "未命名"

def test_tabs_save_and_dedup_id_dir():
    import tempfile
    from core.data.songs import legacy_song_id
    sid = legacy_song_id("知足")
    with tempfile.TemporaryDirectory() as d:
        r1 = tabs_store.save_tab(d, sid, "主歌.png", b"\x89PNG fake")
        r2 = tabs_store.save_tab(d, sid, "主歌.png", b"\x89PNG fake2")
        assert r1 == f"tabs/{sid}/主歌.png"
        assert r2 == f"tabs/{sid}/主歌-1.png"          # 重名自动加后缀
        assert open(os.path.join(d, sid, "主歌-1.png"), "rb").read() == b"\x89PNG fake2"

def test_tabs_save_rejects_bad_ext_and_oversize():
    import tempfile
    from core.data.songs import legacy_song_id
    sid = legacy_song_id("知足")
    with tempfile.TemporaryDirectory() as d:
        for bad in ("谱.exe", "谱", "谱.svg"):
            try:
                tabs_store.save_tab(d, sid, bad, b"x")
                assert False, f"{bad} 应被拦截"
            except ValueError:
                pass
        try:
            tabs_store.save_tab(d, sid, "big.png", b"x" * (tabs_store.MAX_FILE_BYTES + 1))
            assert False, "超尺寸应被拦截"
        except ValueError:
            pass

def test_tabs_save_rejects_invalid_song_id():
    """目录键只接受稳定 song_id：title、空值、路径穿越全部拒绝。"""
    import tempfile
    from core.data.songs import legacy_song_id
    sid = legacy_song_id("知足")
    with tempfile.TemporaryDirectory() as d:
        for bad in ("知足", "", "../x", "song_短"):
            try:
                tabs_store.save_tab(d, bad, "a.png", b"x")
                assert False, f"{bad!r} 应被拒绝"
            except ValueError:
                pass
        try:
            tabs_store.delete_tab(d, "知足", f"tabs/{sid}/a.png")
            assert False, "delete 用 title 应被拒绝"
        except ValueError:
            pass

def test_tabs_delete_traversal_guard_id_dir():
    import tempfile
    from core.data.songs import legacy_song_id
    sid = legacy_song_id("知足")
    other = legacy_song_id("别的歌")
    with tempfile.TemporaryDirectory() as d:
        tabs_root = os.path.join(d, "data", "tabs")  # 与生产一致：relpath 相对 data/
        rel = tabs_store.save_tab(tabs_root, sid, "主歌.png", b"\x89PNG fake")
        assert tabs_store.delete_tab(tabs_root, sid, f"tabs/{sid}/../songs.json") is False
        assert tabs_store.delete_tab(tabs_root, sid, f"tabs/{other}/x.png") is False
        assert tabs_store.delete_tab(tabs_root, sid, rel) is True
        assert tabs_store.delete_tab(tabs_root, sid, rel) is False  # 已删 → False

def test_pinyin_initials():
    from core.data.songs import pinyin_initials
    assert pinyin_initials("知足") == "zz"
    assert pinyin_initials("枫") == "f"

def test_search():
    lib = SongLibrary([Song(title="a"), Song(title="ab")])
    s = lib.search("a")
    assert s.title == "a"
    assert lib.search("c") is None

def test_count():
    lib = SongLibrary([
        Song(title="a", status="active"),
        Song(title="b", status="draft"),
    ])
    assert lib.count_active() == 1
    assert lib.count_draft() == 1


# ═══════ Layout Registry ═══════

def test_layout_registry():
    ls = list_layouts()
    ids = [l["id"] for l in ls]
    assert "grid-wrap" in ids

def test_get_layout():
    l = get_layout("grid-wrap")
    assert l.id == "grid-wrap"

def test_layout_pages():
    assert get_layout("grid-wrap").pages == 2

def test_get_layout_nonexistent():
    try:
        get_layout("no")
        assert False
    except KeyError:
        pass

def test_layout_params():
    keys = [p.key for p in get_layout("grid-wrap").params()]
    assert "margin" in keys
    assert "font_song" in keys


# ═══════ Canvas / background cache correctness ═══════

def test_canvas_avoidance_is_explicit():
    from core.spec import CANVAS_PRESETS, get_canvas_spec
    base = CANVAS_PRESETS["抖音全屏 9:20"]
    assert base.avoid_zones == ()
    assert get_canvas_spec("抖音全屏 9:20", avoid=False).avoid_zones == ()
    assert get_canvas_spec("抖音全屏 9:20", avoid=True).avoid_zones == (
        (940, 1080, 1080, 2400),
    )


def test_bg_cache_separates_avoid_and_mist_inputs():
    import tempfile
    from PIL import Image, ImageChops
    from core.engine import _get_base, clear_bg_cache
    from core.spec import CanvasSpec

    with tempfile.TemporaryDirectory() as d:
        bg = os.path.join(d, "bg.png")
        Image.new("RGB", (24, 1600), (20, 40, 60)).save(bg)
        normal = Style(text=(0, 0, 0), label=(0, 0, 0), pill=(0, 0, 0, 0),
                       line=(0, 0, 0), mist=(255, 255, 255, 40))
        theme = Theme(name="cache-test", dir=d, output_prefix="x",
                      backgrounds={"1": "bg.png", "2": "bg.png"},
                      watermark_fix=False, styles={1: normal, 2: normal})
        spec_normal = CanvasSpec(width=24, height=1600, baseline_height=1600)
        spec_avoid = CanvasSpec(width=24, height=1600, baseline_height=1600,
                                avoid_zones=((20, 1080, 24, 1600),))

        clear_bg_cache()
        avoid_first = _get_base(theme, 1, spec_avoid)
        normal_after = _get_base(theme, 1, spec_normal)
        assert ImageChops.difference(
            avoid_first.convert("RGB"), normal_after.convert("RGB")
        ).getbbox() is not None

        clear_bg_cache()
        normal_first = _get_base(theme, 1, spec_normal)
        avoid_after = _get_base(theme, 1, spec_avoid)
        assert ImageChops.difference(normal_first, normal_after).getbbox() is None
        assert ImageChops.difference(avoid_after, avoid_first).getbbox() is None

        changed = Style(text=(0, 0, 0), label=(0, 0, 0), pill=(0, 0, 0, 0),
                        line=(0, 0, 0), mist=(255, 0, 0, 120))
        theme.styles[1] = changed
        changed_mist = _get_base(theme, 1, spec_normal)
        assert ImageChops.difference(
            normal_after.convert("RGB"), changed_mist.convert("RGB")
        ).getbbox() is not None
        clear_bg_cache()


# ═══════ Grouping Logic ═══════

def test_group_section_override():
    """恋爱ing is 5 chars but section=3 → goes to 三字."""
    lib = SongLibrary([Song(title="恋爱ing", status="active", section=3)])
    from core.layouts.grid_wrap import _group
    g = _group(lib)
    assert "恋爱ing" in g[3]
    assert "恋爱ing" not in g[5]

def test_group_fallback_len():
    lib = SongLibrary([Song(title="枫", status="active")])
    from core.layouts.grid_wrap import _group
    g = _group(lib)
    assert "枫" in g[1]

def test_group_english_to_7():
    lib = SongLibrary([Song(title="Hello", status="active")])
    from core.layouts.grid_wrap import _group
    g = _group(lib)
    assert "Hello" in g[7]

def test_default_library_178():
    lib = build_default_library()
    assert lib.count_active() == 178
    from core.layouts.grid_wrap import _group
    g = _group(lib)
    assert g[1] == ["枫", "耿"]


# ═══════ P1 新模型测试 ═══════

def test_palette_from_style():
    from core.themes.palette import Palette
    from core.style import Style
    s = Style(text=(43, 84, 78), label=(36, 110, 96), pill=(188, 224, 210, 130),
              line=(232, 146, 118), mist=(255, 255, 255, 66))
    p = Palette.from_style(1, s, "测试")
    assert p.text == (43, 84, 78)
    assert p.label == (36, 110, 96)
    assert p.mist == (255, 255, 255, 66)
    assert p.name == "测试"
    assert p.source == "theme"

def test_palette_to_style_dict():
    from core.themes.palette import Palette
    from core.style import Style
    s = Style(text=(43, 84, 78), label=(36, 110, 96), pill=(188, 224, 210, 130),
              line=(232, 146, 118), mist=(255, 255, 255, 66))
    p = Palette.from_style(1, s)
    d = p.to_style_dict()
    assert d["text"] == (43, 84, 78)
    assert set(d.keys()) == {"text", "label", "pill", "line", "mist"}

def test_skin_from_theme():
    import os
    from core.themes.skin import Skin
    from core.themes.loader import load_themes
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    themes = load_themes(os.path.join(_root, "themes"))
    t = themes["海洋柔光"]
    s = Skin.from_theme(t)
    assert s.theme_name == "海洋柔光"
    assert s.layout_id == "grid-wrap"
    assert s.mist_bottom_avoid == 1498
    assert s.mist_bottom_normal == 1410
    assert s.compatibility == "recommended"
    assert s.source == "theme"

def test_preset_default():
    from core.data.presets import Preset, SongQuery
    p = Preset.default()
    assert p.id == "_default"
    assert p.is_default is True
    assert p.layout_id == "grid-wrap"
    assert p.song_query.status == "active"
    assert p.canvas["width"] == 1080

def test_preset_crud():
    import tempfile
    from core.data.presets import Preset, SongQuery, init_presets, save, load, delete, list_all, duplicate
    with tempfile.TemporaryDirectory() as path:
        presets_dir = init_presets(path)
        all_p = list_all(presets_dir)
        assert len(all_p) == 1  # 默认预设
        assert all_p[0]["id"] == "_default"

        p = Preset(
            id="test1",
            name="测试预设",
            layout_id="magazine-flow",
            canvas={"width": 1080, "height": 1920},
        )
        save(p, presets_dir)
        loaded = load("test1", presets_dir)
        assert loaded is not None
        assert loaded.name == "测试预设"
        assert loaded.layout_id == "magazine-flow"

        d = duplicate("test1", "test1-copy", presets_dir, "副本")
        assert d is not None
        assert d.id == "test1-copy"
        assert "副本" in d.name

        delete("test1", presets_dir)
        assert load("test1", presets_dir) is None


# ═══════ R0.5 Tabs title→ID 目录迁移 ═══════

def _sid(title):
    from core.data.songs import legacy_song_id
    return legacy_song_id(title)


def _mk_dir(root, dirname, files: dict):
    d = os.path.join(root, dirname)
    os.makedirs(d, exist_ok=True)
    for name, content in files.items():
        with open(os.path.join(d, name), "wb") as f:
            f.write(content)
    return d


def test_tabs_migration_moves_title_dir():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        sid = _sid("知足")
        _mk_dir(d, "知足", {"主歌.png": b"A", "副歌.png": b"B"})
        id_map = {"知足": sid}
        plan = tabs_store.plan_migration(d, id_map)
        assert [p["dirname"] for p in plan["planned"]] == ["知足"]
        assert plan["conflicts"] == []
        backup = os.path.join(d, "backup")
        rep = tabs_store.migrate_title_dirs(d, id_map, backup_root=backup, apply=True)
        assert rep["errors"] == []
        assert open(os.path.join(d, sid, "主歌.png"), "rb").read() == b"A"
        assert not os.path.isdir(os.path.join(d, "知足"))           # 旧目录已搬走
        assert os.path.isdir(os.path.join(backup, "知足"))          # 进可恢复备份，未删除
        assert rep["moved"][0]["files"] == ["主歌.png", "副歌.png"] or \
               sorted(rep["moved"][0]["files"]) == ["主歌.png", "副歌.png"]

def test_tabs_migration_idempotent():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        sid = _sid("知足")
        _mk_dir(d, "知足", {"主歌.png": b"A"})
        id_map = {"知足": sid}
        backup = os.path.join(d, "backup")
        tabs_store.migrate_title_dirs(d, id_map, backup_root=backup, apply=True)
        snapshot = {sid: sorted(os.listdir(os.path.join(d, sid)))}
        rep2 = tabs_store.migrate_title_dirs(d, id_map, backup_root=backup, apply=True)
        assert rep2["planned"] == []                                # 第二次无可迁目录
        assert rep2["moved"] == []                                  # 不产生第二份关系
        assert sorted(os.listdir(os.path.join(d, sid))) == snapshot[sid]

def test_tabs_migration_conflict_no_overwrite():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        sid = _sid("知足")
        _mk_dir(d, "知足", {"主歌.png": b"OLD"})
        _mk_dir(d, sid, {"主歌.png": b"NEW-DIFFERENT"})
        id_map = {"知足": sid}
        plan = tabs_store.plan_migration(d, id_map)
        assert plan["conflicts"] and plan["planned"] == []          # 冲突 → 整目录停止
        rep = tabs_store.migrate_title_dirs(d, id_map, backup_root=os.path.join(d, "b"), apply=True)
        assert rep["moved"] == []
        assert open(os.path.join(d, sid, "主歌.png"), "rb").read() == b"NEW-DIFFERENT"  # 不覆盖
        assert os.path.isdir(os.path.join(d, "知足"))               # 旧目录保留

def test_tabs_migration_any_conflict_stops_entire_batch():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        sid_ok, sid_bad = _sid("知足"), _sid("温柔")
        _mk_dir(d, "知足", {"主歌.png": b"OK"})
        _mk_dir(d, "温柔", {"主歌.png": b"OLD"})
        _mk_dir(d, sid_bad, {"主歌.png": b"CONFLICT"})
        rep = tabs_store.migrate_title_dirs(
            d, {"知足": sid_ok, "温柔": sid_bad},
            backup_root=os.path.join(d, "backup"), apply=True)
        assert rep["conflicts"]
        assert rep["moved"] == []
        assert os.path.isfile(os.path.join(d, "知足", "主歌.png"))
        assert not os.path.exists(os.path.join(d, sid_ok))
        assert open(os.path.join(d, sid_bad, "主歌.png"), "rb").read() == b"CONFLICT"

def test_tabs_migration_same_content_is_idempotent():
    """目标已存在同名同内容文件 → 视为已迁移，源文件去重，不算冲突。"""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        sid = _sid("知足")
        _mk_dir(d, "知足", {"主歌.png": b"SAME"})
        _mk_dir(d, sid, {"主歌.png": b"SAME"})
        id_map = {"知足": sid}
        rep = tabs_store.migrate_title_dirs(d, id_map, backup_root=os.path.join(d, "b"), apply=True)
        assert rep["conflicts"] == [] and rep["errors"] == []
        assert open(os.path.join(d, sid, "主歌.png"), "rb").read() == b"SAME"
        assert not os.path.isdir(os.path.join(d, "知足"))

def test_tabs_migration_unresolved_reported():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        _mk_dir(d, "幽灵歌", {"x.png": b"X"})
        rep = tabs_store.migrate_title_dirs(d, {}, backup_root=os.path.join(d, "b"), apply=True)
        assert rep["unresolved"] == ["幽灵歌"]                      # 进报告
        assert os.path.isdir(os.path.join(d, "幽灵歌"))             # 保留原地，不丢

def test_tabs_migration_dry_run_no_writes():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        sid = _sid("知足")
        _mk_dir(d, "知足", {"主歌.png": b"A"})
        before = sorted(os.listdir(d))
        rep = tabs_store.migrate_title_dirs(d, {"知足": sid}, apply=False)
        assert rep["planned"] and not os.path.exists(os.path.join(d, sid))
        assert sorted(os.listdir(d)) == before                      # dry-run 零写入

def test_tabs_rewrite_tab_files():
    sid = _sid("知足")
    old = [f"tabs/知足/主歌.png", "tabs/其他/x.png"]
    new = tabs_store.rewrite_tab_files(old, "知足", sid)
    assert new == [f"tabs/{sid}/主歌.png", "tabs/其他/x.png"]       # 只改本歌前缀


# ═══════ R0.5 Preset custom_ids 迁移与校验 ═══════

def test_preset_custom_ids_migration():
    from core.data.presets import Preset, SongQuery, migrate_custom_ids
    sid, sid2 = _sid("知足"), _sid("温柔")
    p = Preset(id="p1", schema_version=1,
               song_query=SongQuery(custom_ids=["知足", sid2, "不存在的歌", "知足"]))
    rep = migrate_custom_ids(p, {"知足": sid, "温柔": sid2})
    assert rep["resolved"] == {"知足": sid}
    assert rep["unresolved"] == ["不存在的歌"]                      # 未匹配不丢
    assert p.song_query.custom_ids == [sid, sid2]                   # 歌名→ID + 去重
    assert p.song_query.unresolved == ["不存在的歌"]
    assert p.schema_version == 2                                    # 版本提升
    rep2 = migrate_custom_ids(p, {"知足": sid})
    assert rep2["changed"] is False                                 # 幂等

def test_preset_custom_ids_validation_rejects_bad():
    import tempfile
    from core.data.presets import Preset, SongQuery, init_presets, save
    with tempfile.TemporaryDirectory() as path:
        presets_dir = init_presets(path)
        for bad in (["知足"], ["song_短"], [_sid("a"), _sid("a")]):
            try:
                save(Preset(id="bad1", song_query=SongQuery(custom_ids=bad)), presets_dir)
                assert False, f"{bad} 应被拒绝"
            except ValueError:
                pass

def test_preset_id_rejects_directory_escape():
    import tempfile
    from core.data.presets import Preset, init_presets, save, load, delete, duplicate
    with tempfile.TemporaryDirectory() as path:
        presets_dir = init_presets(path)
        for bad in ("", ".", "..", "../escape", "a/b", "a\\b", " bad"):
            try:
                save(Preset(id=bad), presets_dir)
                assert False, f"preset_id {bad!r} 应被拒绝"
            except ValueError:
                pass
            assert load(bad, presets_dir) is None
            assert delete(bad, presets_dir) is False
        try:
            duplicate("_default", "../copy", presets_dir)
            assert False, "duplicate 的目标 ID 逃逸应被拒绝"
        except ValueError:
            pass
        assert not os.path.exists(os.path.join(path, "escape"))

def test_tabs_api_resolves_id_first_and_title_as_compatibility():
    import server.routers.songs as songs_router
    song = Song(title="新歌名", id=_sid("旧歌名"),
                tab_files=[f"tabs/{_sid('旧歌名')}/谱.png"])
    request = _request_for_library(SongLibrary([song]))
    by_id = songs_router.api_tab_list(request, song.id)
    by_title = songs_router.api_tab_list(request, song.title)
    assert by_id == by_title
    assert by_id["song_id"] == song.id
    assert by_id["title"] == "新歌名"

def test_tabs_api_identity_collision_prefers_song_id():
    import server.routers.songs as songs_router
    primary_id = _sid("主路径")
    primary = Song(title="主路径歌曲", id=primary_id)
    title_collision = Song(title=primary_id, id=_sid("同名兼容歌曲"))
    request = _request_for_library(SongLibrary([primary, title_collision]))
    result = songs_router.api_tab_list(request, primary_id)
    assert result["song_id"] == primary.id
    assert result["title"] == primary.title

def test_tabs_api_upload_and_delete_use_resolved_song_id():
    import asyncio
    import io
    import tempfile
    from starlette.datastructures import UploadFile
    import server.routers.songs as songs_router

    song = Song(title="可改名歌曲", id=_sid("曲谱主路径"))
    library = SongLibrary([song])
    request = _request_for_library(library)
    old_save = songs_router._save_library
    old_append = songs_router._append_event
    old_events_path = songs_router._events_path
    events = []
    with tempfile.TemporaryDirectory() as data_root:
        try:
            request.app.state.context.paths.tabs_dir = os.path.join(data_root, "tabs")
            songs_router._save_library = lambda context, library: None
            songs_router._events_path = lambda context: os.path.join(data_root, "events.jsonl")
            songs_router._append_event = lambda context, event_type, **kwargs: events.append(
                {"type": event_type, **kwargs})
            upload = UploadFile(io.BytesIO(b"PNG"), filename="主歌.png")
            created = asyncio.run(songs_router.api_tab_upload(request, song.title, upload))
            rel = created["file"]
            assert created["song_id"] == song.id
            assert rel == f"tabs/{song.id}/主歌.png"
            assert os.path.isfile(os.path.join(data_root, rel))

            deleted = songs_router.api_tab_delete(request, song.id, rel)
            assert deleted["tab_files"] == []
            assert not os.path.exists(os.path.join(data_root, rel))
        finally:
            songs_router._save_library = old_save
            songs_router._append_event = old_append
            songs_router._events_path = old_events_path
    assert [event["source"] for event in events] == ["tabs-api", "tabs-api"]
    assert all(event["song_id"] == song.id for event in events)

def test_event_v2_route_idempotency_and_conflict():
    import tempfile
    import server.routers.events as events_router

    song = Song(title="当前歌名", id="song_event_route")
    request = _request_for_library(SongLibrary([song]))
    payload = {
        "type": "song_sung", "event_id": "evt_route_fixed",
        "song_id": song.id, "title_snapshot": "旧歌名",
        "occurred_at": "2026-07-29T01:00:00+08:00", "source": "quick-view",
    }
    with tempfile.TemporaryDirectory() as data_root:
        try:
            request.app.state.context.paths.events_jsonl = os.path.join(data_root, "events.jsonl")
            first = events_router.api_events_report(request, payload)
            second = events_router.api_events_report(request, payload)
            conflict = events_router.api_events_report(
                request, {**payload, "occurred_at": "2026-07-29T01:01:00+08:00"})
        finally:
            pass
    assert first["event"]["event_id"] == "evt_route_fixed"
    assert second["event"] == first["event"]
    assert first["event"]["title_snapshot"] == "当前歌名"
    assert conflict.status_code == 400
    assert b"event_id" in conflict.body

def test_preset_api_rejects_malformed_query_and_protects_default_flag():
    import tempfile
    import core.data.presets as presets_store
    import server.routers.presets as presets_router

    with tempfile.TemporaryDirectory() as data_root:
        presets_dir = presets_store.init_presets(data_root)
        request = _request_for_library(SongLibrary([]))
        request.app.state.context.preset_repository = presets_dir
        try:
            malformed = presets_router.api_presets_save({"name": "坏数据", "song_query": "不是对象"}, request)
            invalid_ids = presets_router.api_presets_save({
                "name": "坏关系", "song_query": {"custom_ids": None},
            }, request)
            ordinary = presets_router.api_presets_save({
                "id": "ordinary", "name": "普通预设", "is_default": True,
            }, request)
            default = presets_router.api_presets_save({
                "id": "_default", "name": "默认预设", "is_default": False,
            }, request)
            saved_ordinary = presets_store.load("ordinary", presets_dir)
            saved_default = presets_store.load("_default", presets_dir)
        finally:
            pass
    assert malformed.status_code == 400
    assert invalid_ids.status_code == 400
    assert ordinary["ok"] is True and saved_ordinary.is_default is False
    assert default["ok"] is True and saved_default.is_default is True

def test_preset_full_fields_roundtrip():
    import tempfile
    from core.data.presets import Preset, SongQuery, init_presets, save, load, duplicate, delete
    with tempfile.TemporaryDirectory() as path:
        presets_dir = init_presets(path)
        p = Preset(
            id="full1", name="完整场景", layout_id="grid-wrap",
            palette_id="pal-1", skin_id="skin-1",
            canvas={"width": 1080, "height": 1920},
            params={"margin": 58, "font_song": 36},
            export={"format": "png", "scale": 2},
            color_overrides={"text": "#111111"},
            song_query=SongQuery(status="all", classify="artist",
                                 sort_by="title", max_songs=30,
                                 custom_ids=[_sid("知足")],
                                 unresolved=["旧歌名"]),
        )
        save(p, presets_dir)
        q = load("full1", presets_dir)
        assert q is not None
        assert q.palette_id == "pal-1" and q.skin_id == "skin-1"
        assert q.canvas == {"width": 1080, "height": 1920}
        assert q.params == {"margin": 58, "font_song": 36}
        assert q.export == {"format": "png", "scale": 2}
        assert q.color_overrides == {"text": "#111111"}
        assert q.song_query.custom_ids == [_sid("知足")]
        assert q.song_query.unresolved == ["旧歌名"]
        assert q.schema_version == 2
        d = duplicate("full1", "full1-copy", presets_dir, "副本")
        assert d is not None and d.song_query.custom_ids == [_sid("知足")]
        assert delete("full1", presets_dir) is True
        assert load("full1", presets_dir) is None
        assert delete("full1", presets_dir) is False                # 不存在 → False（路由 404）


# ═══════ R0.5 迁移器端到端（tools/migrate_data.py）═══════

def _write_v4_songs(data_root, titles_with_tabs):
    """构造最小 v4 songs.json（无 id 字段），返回 data_root。"""
    import json as _json
    os.makedirs(data_root, exist_ok=True)
    payload = {"version": 4, "songs": [
        {"title": t, "tab_files": [f"tabs/{t}/主歌.png"] if t in titles_with_tabs else []}
        for t in titles_with_tabs
    ]}
    with open(os.path.join(data_root, "songs.json"), "w", encoding="utf-8") as f:
        _json.dump(payload, f, ensure_ascii=False, indent=2)


def test_r05_migrator_end_to_end():
    import json as _json
    import tempfile
    from tools.migrate_data import run_r05_migration
    with tempfile.TemporaryDirectory() as d:
        data_root = os.path.join(d, "data")
        _write_v4_songs(data_root, ["知足"])
        sid = _sid("知足")
        _mk_dir(os.path.join(data_root, "tabs"), "知足", {"主歌.png": b"A"})
        # 旧 preset：custom_ids 为歌名
        pdir = os.path.join(data_root, "presets", "legacy1")
        os.makedirs(pdir)
        with open(os.path.join(data_root, "presets", "manifest.json"), "w", encoding="utf-8") as f:
            _json.dump({"legacy1": {"name": "旧预设"}}, f, ensure_ascii=False)
        with open(os.path.join(pdir, "preset.json"), "w", encoding="utf-8") as f:
            _json.dump({"schema_version": 1, "id": "legacy1", "name": "旧预设",
                        "song_query": {"custom_ids": ["知足", "幽灵歌"]}}, f, ensure_ascii=False)

        # 1. dry-run：零写入
        before = sorted(os.listdir(os.path.join(data_root, "tabs")))
        rep = run_r05_migration(data_root, apply=False)
        assert rep["dry_run"] is True
        assert sorted(os.listdir(os.path.join(data_root, "tabs"))) == before
        assert rep["planned"] and rep["presets"]

        # 2. apply：目录搬迁 + tab_files 改写 + v5 持久化 + preset 迁移 + 备份
        rep = run_r05_migration(data_root, apply=True)
        assert rep["conflicts"] == []
        assert os.path.isfile(os.path.join(data_root, "tabs", sid, "主歌.png"))
        assert not os.path.isdir(os.path.join(data_root, "tabs", "知足"))
        saved = _json.load(open(os.path.join(data_root, "songs.json"), encoding="utf-8"))
        assert saved["version"] == 5                                 # v4→v5 持久化
        assert saved["songs"][0]["id"] == sid                        # 确定性 ID
        assert saved["songs"][0]["tab_files"] == [f"tabs/{sid}/主歌.png"]
        migrated = _json.load(open(os.path.join(pdir, "preset.json"), encoding="utf-8"))
        assert migrated["song_query"]["custom_ids"] == [sid]
        assert migrated["song_query"]["unresolved"] == ["幽灵歌"]    # 未解析不丢
        assert migrated["schema_version"] == 2
        assert rep["backups"]                                        # 备份存在
        assert rep["verify"]["remaining_planned"] == 0

        # 3. 重复运行：无副作用
        rep3 = run_r05_migration(data_root, apply=True)
        assert rep3["planned"] == [] and rep3["tab_files_rewritten"] == 0
        assert rep3["presets"] == []


def test_r05_rename_keeps_tabs_preset_and_event_relationships():
    """R0.5 组合回归：改名只改变显示字段，三个长期关系继续使用原 song_id。"""
    import tempfile
    from core.data.presets import Preset, SongQuery, init_presets, save, load
    with tempfile.TemporaryDirectory() as d:
        song = Song(title="旧歌名", id=_sid("旧歌名"))
        library = SongLibrary([song])
        tabs_root = os.path.join(d, "data", "tabs")
        rel = tabs_store.save_tab(tabs_root, song.id, "谱.png", b"TAB")
        song.tab_files.append(rel)
        presets_dir = init_presets(os.path.join(d, "data"))
        save(Preset(id="rename-case",
                    song_query=SongQuery(custom_ids=[song.id])), presets_dir)
        events_path = os.path.join(d, "data", "events.jsonl")
        append_event(events_path, "queue_added", event_id="evt_before_rename",
                     song_id=song.id, title_snapshot=song.title,
                     occurred_at="2026-07-29T00:00:00+08:00", source="test")

        assert library.update_by_id(song.id, {"title": "新歌名"}) is True

        current = library.get_by_id(song.id)
        preset = load("rename-case", presets_dir)
        event = list(iter_events(events_path))[0]
        assert current.title == "新歌名"
        assert current.tab_files == [rel]
        assert os.path.isfile(os.path.join(d, "data", rel))
        assert preset.song_query.custom_ids == [song.id]
        assert event["song_id"] == song.id
        assert event["title_snapshot"] == "旧歌名"  # 历史快照保持发生时标题


# ═══════ Runner ═══════

if __name__ == "__main__":
    import traceback
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    p = f = 0
    for t in tests:
        try:
            t()
            print(f"  ✅ {t.__name__}")
            p += 1
        except Exception as e:
            print(f"  ❌ {t.__name__}: {e}")
            traceback.print_exc()
            f += 1
    print(f"\n{p} passed, {f} failed")
    sys.exit(1 if f else 0)
