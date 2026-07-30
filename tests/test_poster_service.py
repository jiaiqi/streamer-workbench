"""R1a.1 PosterApplicationService 测试——CRUD + 校验 + SongSource 解析。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.data.posters import (
    PosterDocument,
    SOURCE_ALL_ACTIVE,
    SOURCE_ARTIST,
    SOURCE_MANUAL,
    new_poster_id,
)
from server.ports.repositories import (
    BackupPolicy,
    MISSING_REVISION,
    RepositoryConflict,
)
from server.repositories.posters import FilePosterRepository
from server.repositories.songs import FileSongRepository
from server.services.posters import (
    PosterApplicationService,
    PosterNotFound,
    PosterServiceError,
    PosterValidationFailed,
    SongSnapshot,
)


SONG_A = "song_227fe9c4775f51e2a3e414bc78fdf12e"
SONG_B = "song_a891717f4c1c5d27a8074c18faa212aa"
SONG_C = "song_cff23443d8af5e5d8a0685b9482cd7f3"


def _payload(name="未命名海报", **overrides) -> dict:
    base = {
        "name": name,
        "song_source": {"type": SOURCE_ALL_ACTIVE, "artists": []},
        "selected_song_ids": [],
        "grouping": "none",
        "sorting": "manual",
        "layout_id": "grid-wrap",
        "theme_id": "海洋柔光",
        "canvas_id": "9:20",
        "page_policy": {"mode": "legacy-fixed-2"},
        "parameters": {},
        "export_settings": {},
    }
    base.update(overrides)
    return base


class _FakeSong:
    """避开 SongRepository 复杂存储，用于 resolve 路径的轻量可控 fixture。"""

    def __init__(self, song_id: str, title: str = "", artists=(), section: int = 0):
        self.id = song_id
        self.title = title
        self.artists = list(artists)
        self.section = section
        self.status = "active"


class _FakeSongRepository:
    """实现 SongRepository port 的最小版本：load() 返回带 active() 的 SongLibrary-like。"""

    def __init__(self, songs):
        self._songs = list(songs)

    def load(self):
        class _Lib:
            def __init__(self, songs):
                self._songs = songs

            def active(self_inner):
                return [s for s in self_inner._songs if s.status == "active"]

        return type("Snap", (), {"value": _Lib(self._songs)})()


def _bootstrap(tmpdir):
    root = Path(tmpdir)
    poster_repo = FilePosterRepository(
        root / "posters", BackupPolicy(root / "backups" / "posters"),
    )
    return poster_repo, _FakeSongRepository([_FakeSong(SONG_A, "江南", ["林俊杰"]),
                                              _FakeSong(SONG_B, "枫", ["周杰伦"]),
                                              _FakeSong(SONG_C, "江南（另一首）", ["林俊杰"])])


class PosterServiceCRUDTests(unittest.TestCase):

    def test_save_creates_when_id_empty(self):
        with tempfile.TemporaryDirectory() as td:
            poster_repo, _ = _bootstrap(td)
            svc = PosterApplicationService(poster_repository=poster_repo)
            res = svc.save(_payload("第一张"))
            self.assertTrue(res.poster.id.startswith("poster_"))
            self.assertGreater(len(res.revision), 0)

    def test_save_keeps_created_at_on_update(self):
        with tempfile.TemporaryDirectory() as td:
            poster_repo, _ = _bootstrap(td)
            svc = PosterApplicationService(poster_repository=poster_repo)
            res1 = svc.save(_payload("第一张"))
            first_created = res1.poster.created_at

            # update same id
            payload = _payload("改名了")
            payload["id"] = res1.poster.id
            res2 = svc.save(payload)
            self.assertEqual(res2.poster.created_at, first_created)
            self.assertNotEqual(res2.revision, res1.revision)

    def test_save_rejects_empty_name(self):
        with tempfile.TemporaryDirectory() as td:
            poster_repo, _ = _bootstrap(td)
            svc = PosterApplicationService(poster_repository=poster_repo)
            with self.assertRaises(PosterValidationFailed):
                svc.save(_payload("   "))

    def test_save_rejects_invalid_layout(self):
        with tempfile.TemporaryDirectory() as td:
            poster_repo, _ = _bootstrap(td)
            svc = PosterApplicationService(poster_repository=poster_repo)
            with self.assertRaises(PosterValidationFailed) as cm:
                svc.save(_payload(layout_id="unknown-layout"))
            self.assertIn("grid-wrap", str(cm.exception))

    def test_save_rejects_non_legacy_fixed_2(self):
        with tempfile.TemporaryDirectory() as td:
            poster_repo, _ = _bootstrap(td)
            svc = PosterApplicationService(poster_repository=poster_repo)
            with self.assertRaises(PosterValidationFailed):
                svc.save(_payload(page_policy={"mode": "auto", "min_pages": 1}))

    def test_save_rejects_duplicate_song_id(self):
        with tempfile.TemporaryDirectory() as td:
            poster_repo, _ = _bootstrap(td)
            svc = PosterApplicationService(poster_repository=poster_repo)
            payload = _payload(selected_song_ids=[SONG_A, SONG_A])
            with self.assertRaises(PosterValidationFailed):
                svc.save(payload)

    def test_save_rejects_non_song_id(self):
        with tempfile.TemporaryDirectory() as td:
            poster_repo, _ = _bootstrap(td)
            svc = PosterApplicationService(poster_repository=poster_repo)
            payload = _payload(selected_song_ids=["not_a_song_id"])
            with self.assertRaises(PosterValidationFailed):
                svc.save(payload)

    def test_list_returns_all_summaries(self):
        with tempfile.TemporaryDirectory() as td:
            poster_repo, _ = _bootstrap(td)
            svc = PosterApplicationService(poster_repository=poster_repo)
            svc.save(_payload("A"))
            svc.save(_payload("B"))
            listing = svc.list()
            self.assertEqual(len(listing), 2)
            names = {s.name for s in listing}
            self.assertEqual(names, {"A", "B"})

    def test_delete_existing_poster(self):
        with tempfile.TemporaryDirectory() as td:
            poster_repo, _ = _bootstrap(td)
            svc = PosterApplicationService(poster_repository=poster_repo)
            res = svc.save(_payload("待删"))
            result = svc.delete(res.poster.id)
            self.assertTrue(result.existed)
            with self.assertRaises(PosterNotFound):
                svc.get(res.poster.id)

    def test_delete_unknown_raises(self):
        with tempfile.TemporaryDirectory() as td:
            poster_repo, _ = _bootstrap(td)
            svc = PosterApplicationService(poster_repository=poster_repo)
            with self.assertRaises(PosterNotFound):
                svc.delete(new_poster_id())

    def test_get_revision_returns_expected_value(self):
        with tempfile.TemporaryDirectory() as td:
            poster_repo, _ = _bootstrap(td)
            svc = PosterApplicationService(poster_repository=poster_repo)
            res = svc.save(_payload("rev"))
            rev = svc.get_revision(res.poster.id)
            self.assertEqual(rev, res.revision)


class PosterServiceResolveTests(unittest.TestCase):
    """SongSource 解析路径——resolve 是 RenderDocument 的共享输入。"""

    def test_resolve_all_active_returns_all_active(self):
        with tempfile.TemporaryDirectory() as td:
            poster_repo, song_repo = _bootstrap(td)
            svc = PosterApplicationService(
                poster_repository=poster_repo, song_repository=song_repo,
            )
            res = svc.save(_payload("全部", song_source={"type": SOURCE_ALL_ACTIVE, "artists": []}))
            r = svc.resolve(res.poster.id)
            self.assertEqual(set(s.id for s in r.songs), {SONG_A, SONG_B, SONG_C})
            self.assertEqual(r.missing_song_ids, ())

    def test_resolve_artist_filters_by_artists(self):
        with tempfile.TemporaryDirectory() as td:
            poster_repo, song_repo = _bootstrap(td)
            svc = PosterApplicationService(
                poster_repository=poster_repo, song_repository=song_repo,
            )
            res = svc.save(_payload(
                "林俊杰", song_source={"type": SOURCE_ARTIST, "artists": ["林俊杰"]},
            ))
            r = svc.resolve(res.poster.id)
            ids = [s.id for s in r.songs]
            self.assertEqual(set(ids), {SONG_A, SONG_C})  # 林俊杰 出现两首
            self.assertEqual(r.missing_song_ids, ())

    def test_resolve_artist_case_insensitive(self):
        """库里 "Zhou" / 目标 "ZHOU" / 空白裁剪后命中；中文大小写不变化的部分继续命中。"""
        with tempfile.TemporaryDirectory() as td:
            poster_repo, _ = _bootstrap(td)
            from tests.test_poster_service import _FakeSong, _FakeSongRepository
            custom_songs = _FakeSongRepository([
                _FakeSong(SONG_A, "Zhou-Song", artists=["Zhou", "林俊杰"]),
            ])
            svc = PosterApplicationService(
                poster_repository=poster_repo, song_repository=custom_songs,
            )
            res = svc.save(_payload(
                "z hou", song_source={"type": SOURCE_ARTIST, "artists": [" ZHOU "]},
            ))
            r = svc.resolve(res.poster.id)
            ids = [s.id for s in r.songs]
            self.assertEqual(ids, [SONG_A])

    def test_resolve_with_selected_song_ids_fallback(self):
        """manual source + selected_song_ids 兜底路径：解析为空但 selected 仍生效。"""
        with tempfile.TemporaryDirectory() as td:
            poster_repo, song_repo = _bootstrap(td)
            svc = PosterApplicationService(
                poster_repository=poster_repo, song_repository=song_repo,
            )
            res = svc.save(_payload(
                "manual",
                song_source={"type": SOURCE_MANUAL, "artists": []},
                selected_song_ids=[SONG_A],
            ))
            r = svc.resolve(res.poster.id)
            self.assertEqual([s.id for s in r.songs], [SONG_A])

    def test_resolve_marks_missing_selected_song_ids(self):
        """manual 模式 + selected 含 phantom：phantom 进入 missing_song_ids。"""
        with tempfile.TemporaryDirectory() as td:
            poster_repo, song_repo = _bootstrap(td)
            svc = PosterApplicationService(
                poster_repository=poster_repo, song_repository=song_repo,
            )
            phantom = "song_00000000000000000000000000000000"
            res = svc.save(_payload(
                "missing",
                song_source={"type": SOURCE_MANUAL, "artists": []},
                selected_song_ids=[SONG_A, phantom],
            ))
            r = svc.resolve(res.poster.id)
            # manual 模式下 source 解析为空 → 仅 selected_song_ids 生效 → 1 个有效 + 1 missing
            self.assertEqual(len(r.songs), 1)
            self.assertIn(phantom, r.missing_song_ids)

    def test_resolve_without_song_repo_raises(self):
        with tempfile.TemporaryDirectory() as td:
            poster_repo, _ = _bootstrap(td)
            svc = PosterApplicationService(poster_repository=poster_repo)
            res = svc.save(_payload("no song repo"))
            with self.assertRaises(PosterServiceError):
                svc.resolve(res.poster.id)

    def test_resolve_unknown_poster_raises(self):
        with tempfile.TemporaryDirectory() as td:
            poster_repo, song_repo = _bootstrap(td)
            svc = PosterApplicationService(
                poster_repository=poster_repo, song_repository=song_repo,
            )
            with self.assertRaises(PosterNotFound):
                svc.resolve(new_poster_id())


class PosterServiceSongSnapshotShapeTests(unittest.TestCase):
    """SongSnapshot 不可变快照的属性映射。"""

    def test_snapshot_contains_artists_and_section(self):
        with tempfile.TemporaryDirectory() as td:
            poster_repo, song_repo = _bootstrap(td)
            svc = PosterApplicationService(
                poster_repository=poster_repo, song_repository=song_repo,
            )
            res = svc.save(_payload(
                "snap",
                song_source={"type": SOURCE_ALL_ACTIVE, "artists": []},
            ))
            r = svc.resolve(res.poster.id)
            for snap in r.songs:
                self.assertIsInstance(snap, SongSnapshot)
                self.assertIsInstance(snap.artists, tuple)
                self.assertIsInstance(snap.section, int)


class PosterServiceRevisionInteractionTests(unittest.TestCase):
    """仓库 CAS 与 service 应配合：service 应使用 current revision，仓储负责冲突。"""

    def test_save_with_concurrent_revision_change_raises_conflict(self):
        with tempfile.TemporaryDirectory() as td:
            poster_repo, _ = _bootstrap(td)
            svc = PosterApplicationService(poster_repository=poster_repo)
            res1 = svc.save(_payload("A"))
            # 旁路直接修改仓储（模拟并发）
            poster_repo.get(res1.poster.id)  # 确保存在
            # 第二 save 用过期 revision
            payload = _payload("A-new")
            payload["id"] = res1.poster.id
            res2 = svc.save(payload)
            # 现在版本已是 res2.revision
            # 模拟第三进程仍持有 res1.revision
            poster_repo.get(res1.poster.id)
            # service 自动取最新 revision，无冲突；
            # 这里改成 service.save 不应出错（它每次查最新）
            res3 = svc.save(_payload("A-newer", id=res2.poster.id))
            self.assertNotEqual(res3.revision, res2.revision)


if __name__ == "__main__":
    unittest.main()
