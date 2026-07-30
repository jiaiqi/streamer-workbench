"""R1a.1 FilePosterRepository 测试——原子写、CAS、列表、删除与启动恢复。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.data.posters import (
    PosterDocument,
    SongSource,
    SOURCE_MANUAL,
    SOURCE_ARTIST,
    new_poster_id,
)
from server.ports.repositories import (
    BackupPolicy,
    MISSING_REVISION,
    RepositoryClosed,
    RepositoryConflict,
    RepositoryCorrupt,
    RepositoryUnavailable,
)
from server.repositories.atomic_json import AtomicJsonWriter, json_revision
from server.repositories.posters import (
    FilePosterRepository,
    PosterFaultInjector,
)


SONG_A = "song_227fe9c4775f51e2a3e414bc78fdf12e"
SONG_B = "song_a891717f4c1c5d27a8074c18faa212aa"


def make_poster(
    poster_id: str,
    name: str = "未命名海报",
    *,
    song_ids: list[str] | None = None,
) -> PosterDocument:
    doc = PosterDocument.default(name)
    doc.id = poster_id
    doc.selected_song_ids = song_ids or [SONG_A]
    doc.theme_id = "海洋柔光"
    doc.canvas_id = "9:20"
    doc.created_at = "2026-07-30T10:00:00"
    doc.updated_at = "2026-07-30T10:00:00"
    return doc


def backup_policy(root: Path) -> BackupPolicy:
    return BackupPolicy(root / "backups", keep=3)


class FilePosterRepositoryCrudTests(unittest.TestCase):

    def test_save_then_get_roundtrip(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = FilePosterRepository(root / "posters", backup_policy(root))
            doc = make_poster("p1", "我的第一张", song_ids=[SONG_A, SONG_B])
            snap = repo.save(doc, expected_revision=MISSING_REVISION)

            self.assertEqual(snap.value.id, "p1")
            self.assertEqual(snap.value.name, "我的第一张")
            self.assertEqual(snap.value.selected_song_ids, [SONG_A, SONG_B])

            loaded = repo.get("p1")
            assert loaded is not None
            self.assertEqual(loaded.value.name, "我的第一张")
            self.assertEqual(loaded.value.selected_song_ids, [SONG_A, SONG_B])

    def test_list_returns_summaries_sorted_by_updated_at_desc(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = FilePosterRepository(root / "posters", backup_policy(root))
            repo.save(make_poster("p_earlier", "早的"), expected_revision=MISSING_REVISION)
            repo.save(make_poster("p_later", "晚的"), expected_revision=MISSING_REVISION)
            snap = repo.list()
            ids = [s.id for s in snap.value]
            self.assertEqual(ids, ["p_later", "p_earlier"])
            self.assertEqual(snap.value[0].song_count, 1)
            self.assertEqual(snap.value[0].theme_id, "海洋柔光")

    def test_get_returns_none_for_unknown_id(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = FilePosterRepository(root / "posters", backup_policy(root))
            self.assertIsNone(repo.get("not_exist"))

    def test_get_rejects_invalid_id(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = FilePosterRepository(root / "posters", backup_policy(root))
            self.assertIsNone(repo.get("../escape"))

    def test_delete_soft_moves_to_trash(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = FilePosterRepository(root / "posters", backup_policy(root))
            snap = repo.save(make_poster("p1"), expected_revision=MISSING_REVISION)
            deleted = repo.delete("p1", expected_revision=snap.revision)
            self.assertTrue(deleted)
            self.assertIsNone(repo.get("p1"))
            # 物理移入 .trash
            self.assertTrue((root / "posters" / ".trash").exists())
            trash_entries = list((root / "posters" / ".trash").iterdir())
            self.assertEqual(len(trash_entries), 1)
            self.assertTrue(trash_entries[0].name.startswith("p1"))

    def test_delete_nonexistent_returns_false(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = FilePosterRepository(root / "posters", backup_policy(root))
            self.assertFalse(repo.delete("ghost", expected_revision=MISSING_REVISION))

    def test_save_rejects_invalid_poster_with_mismatched_id(self):
        """写入校验再次拦截——已写入 manifest 后被 validate 拒绝也应回滚。"""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = FilePosterRepository(root / "posters", backup_policy(root))
            bad = make_poster("p_bad")
            bad.layout_id = "magazine-flow"  # P1 不接受
            with self.assertRaises(ValueError):
                repo.save(bad, expected_revision=MISSING_REVISION)
            self.assertIsNone(repo.get("p_bad"))

    def test_save_rejects_invalid_song_ids(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = FilePosterRepository(root / "posters", backup_policy(root))
            bad = make_poster("p_bad", song_ids=[SONG_A, "not_a_song_id"])
            with self.assertRaises(ValueError):
                repo.save(bad, expected_revision=MISSING_REVISION)


class FilePosterRepositoryCASTests(unittest.TestCase):
    """revision 不匹配必须抛 RepositoryConflict，绝不静默覆盖。"""

    def test_conflict_when_expected_missing_but_current_exists(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = FilePosterRepository(root / "posters", backup_policy(root))
            snap = repo.save(make_poster("p1"), expected_revision=MISSING_REVISION)

            # 现在 p1 存在，当前 revision = snap.revision
            # 用 MISSING_REVISION 重写 → 必须冲突
            with self.assertRaises(RepositoryConflict):
                repo.save(make_poster("p1"), expected_revision=MISSING_REVISION)

            # 旧值未被覆盖
            loaded = repo.get("p1")
            assert loaded is not None
            self.assertEqual(loaded.revision, snap.revision)

    def test_concurrent_save_optimistic_locking(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = FilePosterRepository(root / "posters", backup_policy(root))
            snap_a = repo.save(make_poster("p1", "first"), expected_revision=MISSING_REVISION)
            # 第二次 save 改 name 让 payload 产生不同 hash
            doc2 = make_poster("p1", "second")
            snap_b = repo.save(doc2, expected_revision=snap_a.revision)
            self.assertNotEqual(snap_a.revision, snap_b.revision)
            # 第三次 save 用 snap_a.revision（陈旧）应失败
            with self.assertRaises(RepositoryConflict):
                repo.save(make_poster("p1", "third"), expected_revision=snap_a.revision)

    def test_revision_matches_payload_hash(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = FilePosterRepository(root / "posters", backup_policy(root))
            doc = make_poster("p1", "hash-check")
            snap = repo.save(doc, expected_revision=MISSING_REVISION)
            expected_rev = json_revision(doc.to_dict())
            self.assertEqual(snap.revision, expected_rev)


class FilePosterRepositoryBackupTests(unittest.TestCase):
    """每次写入前是否产生备份。"""

    def test_backup_created_on_rewrite(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = FilePosterRepository(root / "posters", backup_policy(root))
            snap1 = repo.save(make_poster("p1", "first"), expected_revision=MISSING_REVISION)
            snap2 = repo.save(make_poster("p1", "second"), expected_revision=snap1.revision)
            # 备份文件命名由 AtomicJsonWriter 决定：{kind}-{timestamp}-{uuid}.json
            backup_dir = root / "backups"
            self.assertTrue(backup_dir.exists())
            backups = list(backup_dir.glob("poster-p1-*.json"))
            self.assertGreater(len(backups), 0)


class FilePosterRepositoryRecoveryTests(unittest.TestCase):
    """启动恢复：清理孤儿 .tmp 文件，重建 manifest。"""

    def test_recover_cleans_orphan_tmp_files(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            poster_root = root / "posters"
            poster_root.mkdir()
            # 先建空 manifest 让 FilePosterRepository.__init__ 能跑过 ensure_root
            (poster_root / "manifest.json").write_text("{}", encoding="utf-8")
            # 注入孤儿文件
            (poster_root / "ghost.tmp").write_text("stale", encoding="utf-8")

            repo = FilePosterRepository(poster_root, backup_policy(root))
            self.assertFalse((poster_root / "ghost.tmp").exists())

    def test_recover_returns_report_when_called_explicitly(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            poster_root = root / "posters"
            poster_root.mkdir()
            (poster_root / "ghost.tmp").write_text("stale", encoding="utf-8")

            repo = FilePosterRepository(poster_root, backup_policy(root))
            # 现在再制造一个新孤儿，重显式调用
            (poster_root / "another.tmp").write_text("stale2", encoding="utf-8")
            report = repo.recover()
            self.assertTrue(any("another.tmp" in d for d in report.recovered))
            self.assertFalse((poster_root / "another.tmp").exists())

    def test_close_marks_closed_and_blocks_subsequent_use(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = FilePosterRepository(root / "posters", backup_policy(root))
            repo.close()
            with self.assertRaises(RepositoryClosed):
                repo.list()


class FilePosterRepositoryAtomicTests(unittest.TestCase):
    """原子写：写入失败不会污染文件。"""

    def test_writer_crash_before_replace_keeps_old_file(self):
        """模拟写中途崩溃；旧文件必须保留，新内容不出现。"""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            # 写一次先建立文件
            repo_ok = FilePosterRepository(root / "posters", backup_policy(root))
            snap = repo_ok.save(make_poster("p1", "good"), expected_revision=MISSING_REVISION)
            repo_ok.close()

            # 读出原内容用于断言
            old_file = root / "posters" / "p1" / "poster.json"
            old_text = old_file.read_text(encoding="utf-8")

            # 新实例，注入 after_temp_fsync 之后崩溃（在 os.replace 之前）
            injector = PosterFaultInjector(fail_at="after_temp_fsync")
            writer = AtomicJsonWriter(fault_injector=injector)
            repo = FilePosterRepository(
                root / "posters", backup_policy(root), writer=writer,
            )
            # writer 包成 RepositoryUnavailable：原 OSError 不外露，这是 R0.7 的兜底
            with self.assertRaises((OSError, RepositoryUnavailable)):
                bad = make_poster("p1", "should_not_persist")
                repo.save(bad, expected_revision=snap.revision)

            # 旧值仍存在
            self.assertEqual(old_file.read_text(encoding="utf-8"), old_text)


class FilePosterRepositoryFaultInjectTests(unittest.TestCase):
    """pre-write 注入点用于压测；post-write 用于写入后注入。"""

    def test_pre_write_crash_leaves_no_poster(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            injector = PosterFaultInjector(fail_at="pre-write")
            repo = FilePosterRepository(
                root / "posters", backup_policy(root), fault_injector=injector,
            )
            with self.assertRaises(OSError):
                repo.save(make_poster("p1"), expected_revision=MISSING_REVISION)
            self.assertIsNone(repo.get("p1"))


if __name__ == "__main__":
    unittest.main()
