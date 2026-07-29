"""R0.7 RenderDocument 与冻结导出任务边界。"""
from __future__ import annotations

import os
import tempfile
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


def _run():
    tests = [value for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print(f"  ✅ {test.__name__}")
    print(f"\n{len(tests)} passed, 0 failed")


if __name__ == "__main__":
    _run()
