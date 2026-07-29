"""R0.7 曲谱附件跨资源事务、回滚与启动恢复测试。"""

from __future__ import annotations

import asyncio
import json
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from core.data.songs import Song, SongLibrary
from server.app import create_app
from server.config import AppConfig
from server.ports.repositories import BackupPolicy, RepositoryConflict
from server.repositories.events import FileEventStore
from server.repositories.songs import FileSongRepository
from server.services.tabs import TabApplicationService, TabRecoveryRequired


SONG_ID = "song_0123456789abcdef0123456789abcdef"
PROJECT = Path(__file__).resolve().parent.parent


class SimulatedCrash(BaseException):
    pass


class FailingSaveRepository:
    def __init__(self, delegate):
        self.delegate = delegate

    def load(self):
        return self.delegate.load()

    def save(self, value, *, expected_revision):
        raise RepositoryConflict("injected CAS failure")


class AppendThenFailOnceEventStore:
    def __init__(self, delegate):
        self.delegate = delegate
        self.failed = False

    def append(self, event):
        result = self.delegate.append(event)
        if not self.failed:
            self.failed = True
            raise OSError("injected response loss after durable append")
        return result


def _resources(root: Path):
    songs = FileSongRepository(
        root / "songs.json", BackupPolicy(root / "backups" / "songs"))
    songs.save(
        SongLibrary([Song("测试歌曲", id=SONG_ID, status="active")]),
        expected_revision=None,
    )
    events = FileEventStore(root / "events.jsonl")
    return songs, events


def _service(root: Path, songs, events, fault=None):
    return TabApplicationService(
        song_repository=songs,
        event_store=events,
        tabs_root=root / "tabs",
        transactions_root=root / "backups" / "tab-transactions",
        fault_injector=fault,
    )


def _journal_phases(root: Path):
    phases = []
    for path in (root / "backups" / "tab-transactions").glob(
            "tabtx_*/journal.json"):
        phases.append(json.loads(path.read_text(encoding="utf-8"))["phase"])
    return sorted(phases)


def test_successful_upload_and_delete_keep_file_metadata_and_events_consistent():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        songs, events = _resources(root)
        service = _service(root, songs, events)
        created = service.upload(SONG_ID, "主歌.png", b"PNG")
        target = root / created.file
        assert target.read_bytes() == b"PNG"
        assert songs.load().value.get_by_id(SONG_ID).tab_files == [created.file]

        deleted = service.delete("测试歌曲", created.file)
        assert deleted.tab_files == ()
        assert not target.exists()
        assert songs.load().value.get_by_id(SONG_ID).tab_files == []
        assert len(events.tail(limit=10, event_type="song_edited")) == 2
        assert _journal_phases(root) == ["committed", "committed"]
        # 删除内容保留在事务可恢复区，不做不可逆 unlink。
        assert any(path.name == "content" for path in (
            root / "backups" / "tab-transactions").glob("tabtx_*/content"))
        songs.close()
        events.close()


def test_real_http_upload_list_and_delete_vertical_slice():
    async def scenario():
        with tempfile.TemporaryDirectory() as raw:
            data_root = Path(raw) / "data"
            app = create_app(AppConfig(
                PROJECT, mode="test", data_root=data_root))
            async with app.router.lifespan_context(app):
                status, created_song = await _http_request(
                    app, "POST", "/api/songs/add",
                    json.dumps({
                        "title": "HTTP 曲谱测试", "status": "active",
                    }, ensure_ascii=False).encode("utf-8"),
                    "application/json",
                )
                assert status == 200
                song_id = created_song["song"]["id"]

                boundary = "streamer-workbench-boundary"
                multipart = (
                    f"--{boundary}\r\n"
                    "Content-Disposition: form-data; name=\"file\"; "
                    "filename=\"HTTP 主歌.png\"\r\n"
                    "Content-Type: image/png\r\n\r\n"
                ).encode("utf-8") + b"PNG\r\n" + (
                    f"--{boundary}--\r\n").encode("ascii")
                status, uploaded = await _http_request(
                    app, "POST", f"/api/songs/{song_id}/tabs",
                    multipart, f"multipart/form-data; boundary={boundary}")
                assert status == 200, uploaded
                relative_path = uploaded["file"]
                assert (data_root / relative_path).is_file()

                status, listed = await _http_request(
                    app, "GET", f"/api/songs/{song_id}/tabs")
                assert status == 200
                assert listed["tab_files"] == [relative_path]

                query = urlencode({"file": relative_path})
                status, deleted = await _http_request(
                    app, "DELETE", f"/api/songs/{song_id}/tabs?{query}")
                assert status == 200, deleted
                assert deleted["tab_files"] == []
                assert not (data_root / relative_path).exists()

    asyncio.run(scenario())


def test_real_http_tabs_errors_use_envelope_and_validate_mime():
    async def scenario():
        with tempfile.TemporaryDirectory() as raw:
            data_root = Path(raw) / "data"
            app = create_app(AppConfig(
                PROJECT, mode="test", data_root=data_root))
            async with app.router.lifespan_context(app):
                status, missing = await _http_request(
                    app, "GET", f"/api/songs/{SONG_ID}/tabs")
                assert status == 404
                assert missing["error"]["code"] == "tab_not_found"
                assert missing["error"]["request_id"].startswith("req_")

                status, created_song = await _http_request(
                    app, "POST", "/api/songs/add",
                    json.dumps({"title": "MIME 测试"}, ensure_ascii=False).encode(),
                    "application/json",
                )
                assert status == 200
                song_id = created_song["song"]["id"]
                boundary = "mime-boundary"
                multipart = (
                    f"--{boundary}\r\n"
                    "Content-Disposition: form-data; name=\"file\"; "
                    "filename=\"伪装.png\"\r\n"
                    "Content-Type: application/pdf\r\n\r\n"
                    "%PDF-test\r\n"
                    f"--{boundary}--\r\n"
                ).encode("utf-8")
                status, mismatch = await _http_request(
                    app, "POST", f"/api/songs/{song_id}/tabs", multipart,
                    f"multipart/form-data; boundary={boundary}")
                assert status == 400
                assert mismatch["error"]["code"] == "tab_validation_failed"

    asyncio.run(scenario())


async def _http_request(
    app, method: str, path: str, body: bytes = b"",
    content_type: str = "application/json",
):
    target = urlsplit(path)
    sent = False
    messages = []

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body,
                    "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)

    await app({
        "type": "http", "asgi": {"version": "3.0"},
        "http_version": "1.1", "method": method, "scheme": "http",
        "path": target.path, "raw_path": target.path.encode("utf-8"),
        "query_string": target.query.encode("utf-8"),
        "headers": [(b"content-type", content_type.encode("utf-8"))],
        "client": ("test", 1), "server": ("test", 80),
    }, receive, send)
    status = next(message["status"] for message in messages
                  if message["type"] == "http.response.start")
    response_body = b"".join(
        message.get("body", b"") for message in messages
        if message["type"] == "http.response.body")
    return status, json.loads(response_body) if response_body else None


def test_upload_repository_conflict_removes_visible_file_and_keeps_metadata_old():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        songs, events = _resources(root)
        service = _service(root, FailingSaveRepository(songs), events)
        try:
            service.upload(SONG_ID, "冲突.png", b"PNG")
            assert False, "Repository 冲突必须失败"
        except RepositoryConflict:
            pass
        assert not list((root / "tabs").rglob("*.png"))
        assert songs.load().value.get_by_id(SONG_ID).tab_files == []
        assert events.tail(limit=10, event_type="song_edited") == ()
        assert _journal_phases(root) == ["rolled_back"]
        songs.close()
        events.close()


def test_two_service_instances_serialize_same_root_same_name_uploads():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        songs, events = _resources(root)
        second_songs = FileSongRepository(
            root / "songs.json", BackupPolicy(root / "backups" / "songs-2"))
        second_events = FileEventStore(root / "events.jsonl")
        services = (
            _service(root, songs, events),
            _service(root, second_songs, second_events),
        )
        barrier = threading.Barrier(2)
        results = []
        failures = []

        def upload(service, content):
            try:
                barrier.wait()
                results.append(service.upload(
                    SONG_ID, "同名.png", content).file)
            except Exception as error:
                failures.append(error)

        workers = [
            threading.Thread(target=upload, args=(services[0], b"ONE")),
            threading.Thread(target=upload, args=(services[1], b"TWO")),
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()

        assert failures == []
        assert sorted(results) == [
            f"tabs/{SONG_ID}/同名-1.png",
            f"tabs/{SONG_ID}/同名.png",
        ]
        library_paths = songs.load().value.get_by_id(SONG_ID).tab_files
        assert sorted(library_paths) == sorted(results)
        assert {(root / path).read_bytes() for path in results} == {b"ONE", b"TWO"}
        assert len(events.tail(limit=10, event_type="song_edited")) == 2
        songs.close()
        second_songs.close()
        events.close()
        second_events.close()


def test_delete_repository_conflict_restores_original_file_and_metadata():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        songs, events = _resources(root)
        created = _service(root, songs, events).upload(
            SONG_ID, "需要恢复.png", b"TAB")
        service = _service(root, FailingSaveRepository(songs), events)
        try:
            service.delete(SONG_ID, created.file)
            assert False, "Repository 冲突必须失败"
        except RepositoryConflict:
            pass
        assert (root / created.file).read_bytes() == b"TAB"
        assert songs.load().value.get_by_id(SONG_ID).tab_files == [created.file]
        assert len(events.tail(limit=10, event_type="song_edited")) == 1
        assert _journal_phases(root) == ["committed", "rolled_back"]
        songs.close()
        events.close()


def test_restart_rolls_back_upload_crash_after_file_publish():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        songs, events = _resources(root)

        def crash(phase):
            if phase == "after_file_publish":
                raise SimulatedCrash()

        try:
            _service(root, songs, events, crash).upload(
                SONG_ID, "半成品.png", b"PNG")
            assert False, "故障注入必须中断"
        except SimulatedCrash:
            pass
        assert list((root / "tabs").rglob("*.png"))
        assert songs.load().value.get_by_id(SONG_ID).tab_files == []

        report = _service(root, songs, events).recover()
        assert len(report.rolled_back) == 1 and report.unresolved == ()
        assert not list((root / "tabs").rglob("*.png"))
        assert events.tail(limit=10, event_type="song_edited") == ()
        assert _journal_phases(root) == ["rolled_back"]
        songs.close()
        events.close()


def test_restart_finishes_upload_crash_after_metadata_publish_idempotently():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        songs, events = _resources(root)

        def crash(phase):
            if phase == "after_metadata_publish":
                raise SimulatedCrash()

        try:
            _service(root, songs, events, crash).upload(
                SONG_ID, "已提交.png", b"PNG")
            assert False, "故障注入必须中断"
        except SimulatedCrash:
            pass
        relative = songs.load().value.get_by_id(SONG_ID).tab_files[0]
        assert (root / relative).is_file()
        assert events.tail(limit=10, event_type="song_edited") == ()

        first = _service(root, songs, events).recover()
        second = _service(root, songs, events).recover()
        assert len(first.committed) == 1 and first.unresolved == ()
        assert second == type(second)()
        stored_events = events.tail(limit=10, event_type="song_edited")
        assert len(stored_events) == 1
        assert stored_events[0]["meta"]["changes"][0]["new"] == relative
        assert _journal_phases(root) == ["committed"]
        songs.close()
        events.close()


def test_restart_finishes_delete_crash_after_metadata_publish():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        songs, events = _resources(root)
        created = _service(root, songs, events).upload(
            SONG_ID, "待删除.png", b"TAB")

        def crash(phase):
            if phase == "after_metadata_publish":
                raise SimulatedCrash()

        try:
            _service(root, songs, events, crash).delete(
                SONG_ID, created.file)
            assert False, "故障注入必须中断"
        except SimulatedCrash:
            pass
        assert songs.load().value.get_by_id(SONG_ID).tab_files == []
        assert not (root / created.file).exists()

        report = _service(root, songs, events).recover()
        assert len(report.committed) == 1 and report.unresolved == ()
        stored_events = events.tail(limit=10, event_type="song_edited")
        assert len(stored_events) == 2
        delete_events = [event for event in stored_events
                         if event["meta"]["changes"][0]["old"] == created.file]
        assert len(delete_events) == 1
        assert _journal_phases(root) == ["committed", "committed"]
        songs.close()
        events.close()


def test_restart_rolls_back_delete_crash_after_file_stage():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        songs, events = _resources(root)
        created = _service(root, songs, events).upload(
            SONG_ID, "暂存中断.png", b"TAB")

        def crash(phase):
            if phase == "after_file_stage":
                raise SimulatedCrash()

        try:
            _service(root, songs, events, crash).delete(SONG_ID, created.file)
            assert False, "故障注入必须中断"
        except SimulatedCrash:
            pass
        report = _service(root, songs, events).recover()
        assert len(report.rolled_back) == 1 and report.unresolved == ()
        assert (root / created.file).read_bytes() == b"TAB"
        assert songs.load().value.get_by_id(SONG_ID).tab_files == [created.file]
        songs.close()
        events.close()


def test_event_durable_append_then_error_recovers_without_duplicate():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        songs, events = _resources(root)
        flaky_events = AppendThenFailOnceEventStore(events)
        try:
            _service(root, songs, flaky_events).upload(
                SONG_ID, "幂等事件.png", b"PNG")
            assert False, "事件返回失败必须暴露待恢复状态"
        except TabRecoveryRequired:
            pass
        assert len(events.tail(limit=10, event_type="song_edited")) == 1
        report = _service(root, songs, events).recover()
        assert len(report.committed) == 1 and report.unresolved == ()
        assert len(events.tail(limit=10, event_type="song_edited")) == 1
        songs.close()
        events.close()


def test_publish_failure_rolls_back_prepared_transaction():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        songs, events = _resources(root)
        service = _service(root, songs, events)

        def fail(_journal):
            raise OSError("injected publish failure")

        service._publish_upload = fail
        try:
            service.upload(SONG_ID, "发布失败.png", b"PNG")
            assert False, "发布失败必须向调用方暴露"
        except OSError:
            pass
        assert _journal_phases(root) == ["rolled_back"]
        assert not list((root / "tabs").rglob("*.png"))
        assert songs.load().value.get_by_id(SONG_ID).tab_files == []
        songs.close()
        events.close()


def test_recovery_blocks_upload_metadata_whose_physical_file_is_missing():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        songs, events = _resources(root)

        def crash(phase):
            if phase == "after_metadata_publish":
                raise SimulatedCrash()

        try:
            _service(root, songs, events, crash).upload(
                SONG_ID, "丢失.png", b"PNG")
            assert False, "故障注入必须中断"
        except SimulatedCrash:
            pass
        relative = songs.load().value.get_by_id(SONG_ID).tab_files[0]
        (root / relative).unlink()

        report = _service(root, songs, events).recover()
        assert len(report.unresolved) == 1
        assert events.tail(limit=10, event_type="song_edited") == ()
        assert _journal_phases(root) == ["metadata_published"]
        songs.close()
        events.close()


def test_recovery_rejects_unknown_journal_phase_without_guessing():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        songs, events = _resources(root)

        def crash(phase):
            if phase == "after_file_publish":
                raise SimulatedCrash()

        try:
            _service(root, songs, events, crash).upload(
                SONG_ID, "未知阶段.png", b"PNG")
            assert False, "故障注入必须中断"
        except SimulatedCrash:
            pass
        journal_path = next((root / "backups" / "tab-transactions").glob(
            "tabtx_*/journal.json"))
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        journal["phase"] = "future_phase"
        journal_path.write_text(
            json.dumps(journal, ensure_ascii=False), encoding="utf-8")

        report = _service(root, songs, events).recover()
        assert len(report.unresolved) == 1
        assert list((root / "tabs").rglob("*.png"))
        assert events.tail(limit=10, event_type="song_edited") == ()
        songs.close()
        events.close()


def test_recovery_rejects_journal_event_identity_tampering():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        songs, events = _resources(root)

        def crash(phase):
            if phase == "after_metadata_publish":
                raise SimulatedCrash()

        try:
            _service(root, songs, events, crash).upload(
                SONG_ID, "串改事件.png", b"PNG")
            assert False, "故障注入必须中断"
        except SimulatedCrash:
            pass
        journal_path = next((root / "backups" / "tab-transactions").glob(
            "tabtx_*/journal.json"))
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        journal["event"]["song_id"] = "song_ffffffffffffffffffffffffffffffff"
        journal_path.write_text(
            json.dumps(journal, ensure_ascii=False), encoding="utf-8")

        report = _service(root, songs, events).recover()
        assert len(report.unresolved) == 1
        assert events.tail(limit=10, event_type="song_edited") == ()
        songs.close()
        events.close()


def test_recovery_rejects_delete_reference_when_target_and_stage_are_missing():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        songs, events = _resources(root)
        created = _service(root, songs, events).upload(
            SONG_ID, "双缺.png", b"TAB")

        def crash(phase):
            if phase == "after_file_stage":
                raise SimulatedCrash()

        try:
            _service(root, songs, events, crash).delete(SONG_ID, created.file)
            assert False, "故障注入必须中断"
        except SimulatedCrash:
            pass
        staged = next((root / "backups" / "tab-transactions").glob(
            "tabtx_*/content"))
        staged.unlink()
        report = _service(root, songs, events).recover()
        assert len(report.unresolved) == 1
        assert songs.load().value.get_by_id(SONG_ID).tab_files == [created.file]
        songs.close()
        events.close()


def test_recovery_rejects_delete_when_target_and_stage_both_exist():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        songs, events = _resources(root)
        created = _service(root, songs, events).upload(
            SONG_ID, "删除双存.png", b"TAB")

        def crash(phase):
            if phase == "after_metadata_publish":
                raise SimulatedCrash()

        try:
            _service(root, songs, events, crash).delete(SONG_ID, created.file)
            assert False, "故障注入必须中断"
        except SimulatedCrash:
            pass
        staged = next(path for path in (
            root / "backups" / "tab-transactions").glob("tabtx_*/content")
            if path.read_bytes() == b"TAB")
        target = root / created.file
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(staged.read_bytes())
        report = _service(root, songs, events).recover()
        assert len(report.unresolved) == 1
        assert songs.load().value.get_by_id(SONG_ID).tab_files == []
        songs.close()
        events.close()


def test_recovery_rejects_upload_when_target_and_stage_both_exist():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        songs, events = _resources(root)

        def crash(phase):
            if phase == "after_file_publish":
                raise SimulatedCrash()

        try:
            _service(root, songs, events, crash).upload(
                SONG_ID, "上传双存.png", b"PNG")
            assert False, "故障注入必须中断"
        except SimulatedCrash:
            pass
        journal_path = next((root / "backups" / "tab-transactions").glob(
            "tabtx_*/journal.json"))
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        target = root / journal["relative_path"]
        staged = journal_path.parent / "content"
        staged.write_bytes(target.read_bytes())
        report = _service(root, songs, events).recover()
        assert len(report.unresolved) == 1
        assert songs.load().value.get_by_id(SONG_ID).tab_files == []
        songs.close()
        events.close()


def _run():
    tests = [value for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print(f"  ✅ {test.__name__}")
    print(f"\n{len(tests)} passed, 0 failed")


if __name__ == "__main__":
    _run()
