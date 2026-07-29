"""R0.7 RenderDocument 与冻结导出任务边界。"""
from __future__ import annotations

import os
import asyncio
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from core.data.songs import Song, SongLibrary
from core.spec import get_canvas_spec
from core.themes.loader import load_themes
from server.ports.repositories import StoredSnapshot
from server.services.export import ExportJobInput, ExportTarget, run_export_job
from server.services.render_document import build_render_document


PROJECT = Path(__file__).resolve().parent.parent
FONT = PROJECT / "fonts" / "MaokenAssortedSans.ttf"


class RecordingEventStore:
    def __init__(self):
        self.events = []

    def append(self, event):
        self.events.append(event)


def _document(library=None, settings_revision="settings-1"):
    library = library or SongLibrary([Song(
        "冻结歌曲", id="song_00000000000000000000000000000001",
        artists=["原歌手"], tags=["原标签"])])
    theme = load_themes(str(PROJECT / "themes"))["海洋柔光"]
    return build_render_document(
        song_snapshot=StoredSnapshot(library, "songs-1"), theme=theme,
        layout_id="grid-wrap", canvas=get_canvas_spec("标准 9:16"), page=1,
        font_path=str(FONT), settings_revision=settings_revision,
        parameters={"nested": {"items": [1, 2]}},
    ), library, theme


def test_document_is_deeply_immutable_and_detached_from_sources():
    document, library, theme = _document()
    original_id = document.document_id
    library.songs[0].title = "后来改名"
    library.songs[0].artists.append("后来歌手")
    theme.backgrounds["1"] = "later.png"

    assert document.song_snapshots[0].values["title"] == "冻结歌曲"
    assert document.song_snapshots[0].values["artists"] == ("原歌手",)
    assert document.theme.backgrounds["1"] != "later.png"
    assert document.document_id == original_id
    try:
        document.parameters["nested"]["items"] += (3,)
        assert False, "嵌套参数必须不可变"
    except TypeError:
        pass


def test_equivalent_input_has_stable_document_identity_and_revisions():
    first, _, _ = _document()
    second, _, _ = _document()
    assert first == second
    assert first.document_id == second.document_id
    assert first.source_revisions.songs == "songs-1"
    assert first.source_revisions.settings == "settings-1"


def test_preview_and_export_routers_share_the_same_builder():
    import server.routers.export as export_router
    import server.routers.render as render_router

    assert render_router.build_render_document is export_router.build_render_document


def test_export_job_uses_only_frozen_input_and_reports_after_publish():
    document, library, _ = _document()
    library.songs.clear()
    store = RecordingEventStore()
    with tempfile.TemporaryDirectory() as raw:
        target = Path(raw) / "frozen.png"
        state = {"status": "running", "done": 0, "total": 1, "current": "",
                 "files": [], "output_dir": raw, "total_ms": None, "error": None}
        job = ExportJobInput("job-frozen", (document,),
                             (ExportTarget(target, "海洋柔光", 1),), store, state)
        run_export_job(job)
        assert state["status"] == "done"
        assert target.is_file() and target.stat().st_size > 0
        assert store.events[0]["meta"]["document_ids"] == [document.document_id]
        assert not hasattr(job, "request") and not hasattr(job, "context")
        assert not hasattr(job, "repository")


def test_export_failure_does_not_publish_target_or_success_event():
    import server.services.export as export_service

    document, _, _ = _document()
    store = RecordingEventStore()
    old_render = export_service.render_document
    export_service.render_document = lambda _document: (_ for _ in ()).throw(RuntimeError("boom"))
    try:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "failed.png"
            state = {"status": "running", "done": 0, "total": 1, "current": "",
                     "files": [], "output_dir": raw, "total_ms": None, "error": None}
            run_export_job(ExportJobInput(
                "job-failed", (document,), (ExportTarget(target, "主题", 1),), store, state))
            assert state["status"] == "error"
            assert not target.exists()
            assert store.events == []
    finally:
        export_service.render_document = old_render


def _job_state(output_dir: Path, total: int = 1):
    return {"status": "running", "done": 0, "total": total, "current": "",
            "files": [], "output_dir": str(output_dir), "total_ms": None, "error": None}


def _wait_done(state, timeout=10.0):
    deadline = time.monotonic() + timeout
    while state["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert state["status"] == "done", state


def test_two_apps_run_real_exports_with_isolated_jobs_events_and_files():
    from server.app import create_app
    from server.config import AppConfig

    async def scenario():
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            app_a = create_app(AppConfig(PROJECT, mode="test", data_root=base / "a"))
            app_b = create_app(AppConfig(PROJECT, mode="test", data_root=base / "b"))
            async with app_a.router.lifespan_context(app_a):
                async with app_b.router.lifespan_context(app_b):
                    contexts = (app_a.state.context, app_b.state.context)
                    states = []
                    for label, context in zip(("a", "b"), contexts, strict=True):
                        document = build_render_document(
                            song_snapshot=context.song_repository.load(),
                            theme=context.themes["海洋柔光"], layout_id="grid-wrap",
                            canvas=get_canvas_spec("标准 9:16"), page=1,
                            font_path=str(FONT))
                        target = context.paths.data_root / "exports" / f"{label}.png"
                        state = _job_state(target.parent)
                        context.export_job_manager[f"job-{label}"] = state
                        context.export_job_manager.start(ExportJobInput(
                            f"job-{label}", (document,),
                            (ExportTarget(target, "海洋柔光", 1),),
                            context.event_store, state))
                        states.append(state)
                    for state in states:
                        _wait_done(state)
                    assert (base / "a" / "exports" / "a.png").is_file()
                    assert (base / "b" / "exports" / "b.png").is_file()
                    assert not (base / "a" / "exports" / "b.png").exists()
                    assert not (base / "b" / "exports" / "a.png").exists()
                    assert contexts[0].export_job_manager is not contexts[1].export_job_manager
                    for context, job_id in zip(contexts, ("job-a", "job-b"), strict=True):
                        events = context.event_store.tail(limit=10, event_type="poster_exported")
                        assert len(events) == 1 and events[0]["meta"]["job_id"] == job_id
                    assert (base / "a" / "events.jsonl").read_text() != ""
                    assert (base / "b" / "events.jsonl").read_text() != ""

    asyncio.run(scenario())


def test_queued_export_keeps_frozen_song_preset_settings_and_output_target():
    from server.app import create_app
    from server.config import AppConfig

    async def scenario():
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            app = create_app(AppConfig(PROJECT, mode="test", data_root=root / "data"))
            async with app.router.lifespan_context(app):
                context = app.state.context
                songs = context.song_repository.load()
                songs.value.songs.append(Song(
                    "入队前歌名", id="song_00000000000000000000000000000002"))
                context.song_repository.save(songs.value, expected_revision=songs.revision)
                songs = context.song_repository.load()
                settings = context.settings_repository.load()
                preset = context.preset_repository.get("_default")
                old_output = root / "frozen-output"
                document = build_render_document(
                    song_snapshot=songs, theme=context.themes["海洋柔光"],
                    layout_id="grid-wrap", canvas=get_canvas_spec("标准 9:16"), page=1,
                    font_path=str(FONT), settings_revision=settings.revision,
                    preset_revision=preset.revision)
                target = old_output / "frozen.png"
                state = _job_state(old_output)
                job = ExportJobInput("job-snapshot", (document,),
                                     (ExportTarget(target, "海洋柔光", 1),),
                                     context.event_store, state)

                songs.value.songs[0].title = "入队后改名"
                context.song_repository.save(songs.value, expected_revision=songs.revision)
                preset.value.name = "入队后修改预设"
                context.preset_repository.save(preset.value, expected_revision=preset.revision)
                settings.value["output_dir"] = str(root / "new-output")
                context.settings_repository.save(settings.value,
                                                 expected_revision=settings.revision)

                run_export_job(job)
                assert state["status"] == "done"
                assert target.is_file()
                assert not (root / "new-output" / "frozen.png").exists()
                assert document.song_snapshots[0].values["title"] != "入队后改名"
                assert document.source_revisions.preset == preset.revision
                assert document.source_revisions.settings == settings.revision

    asyncio.run(scenario())


def test_server_boundary_imports_have_no_user_data_or_thread_side_effects():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        marker = root / "must-not-exist"
        script = """
import json, pathlib, threading
before = {p.name for p in pathlib.Path.cwd().iterdir()}
threads = len(threading.enumerate())
import server.ports.repositories
import server.repositories.atomic_json
import server.repositories.songs
import server.repositories.settings
import server.repositories.presets
import server.repositories.events
import server.services.render_document
import server.services.export
after = {p.name for p in pathlib.Path.cwd().iterdir()}
print(json.dumps({"created": sorted(after-before), "threads": len(threading.enumerate())-threads}))
"""
        environment = {**os.environ, "HOME": str(root / "home"),
                       "STREAMER_WORKBENCH_DATA_DIR": str(marker),
                       "PYTHONPATH": str(PROJECT)}
        result = subprocess.run([sys.executable, "-c", script], cwd=root,
                                env=environment, text=True, capture_output=True, check=True)
        evidence = json.loads(result.stdout)
        assert evidence == {"created": [], "threads": 0}
        assert not marker.exists() and not (root / "home").exists()


def _run():
    tests = [value for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print(f"  ✅ {test.__name__}")
    print(f"\n{len(tests)} passed, 0 failed")


if __name__ == "__main__":
    _run()
