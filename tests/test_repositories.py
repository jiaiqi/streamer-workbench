"""R0.7 Repository 基础可靠性独立测试。"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.data.songs import Song, SongLibrary
from server.ports.repositories import (
    BackupPolicy,
    RepositoryClosed,
    RepositoryConflict,
    RepositoryUnavailable,
)
from server.repositories.atomic_json import AtomicJsonWriter, FaultInjector, _fsync_directory
from server.repositories.settings import FileSettingsRepository
from server.repositories.songs import FileSongRepository


def policy(root: Path, keep: int = 20) -> BackupPolicy:
    return BackupPolicy(root=root / "backups", keep=keep)


class AtomicJsonWriterTests(unittest.TestCase):
    def test_directory_fsync_unsupported_is_safe_degradation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with patch("server.repositories.atomic_json.os.open", side_effect=OSError("unsupported")):
                _fsync_directory(Path(raw))

    def test_all_fault_points_preserve_old_target(self) -> None:
        phases = (
            "before_temp_write",
            "after_temp_write",
            "before_temp_flush",
            "before_temp_fsync",
            "after_temp_fsync",
            "after_validate",
            "before_backup_write",
            "after_backup",
            "before_replace",
            "after_replace",
            "before_directory_fsync",
            "after_directory_fsync",
            "after_verify",
        )
        for phase in phases:
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                target = root / "data" / "value.json"
                target.parent.mkdir()
                original = {"version": 1, "value": "旧值"}
                target.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
                writer = AtomicJsonWriter(FaultInjector(phase))

                with self.assertRaises(RepositoryUnavailable):
                    writer.write(
                        target,
                        {"version": 1, "value": "新值"},
                        validator=lambda value: None,
                        backup_policy=policy(root),
                        backup_kind="test",
                    )

                self.assertEqual(json.loads(target.read_text(encoding="utf-8")), original)
                self.assertEqual(list(target.parent.glob(".*.tmp")), [])

    def test_success_creates_unique_valid_backups_and_trims(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target = root / "value.json"
            target.write_text('{"value": 0}', encoding="utf-8")
            writer = AtomicJsonWriter()
            backup_policy = policy(root, keep=2)
            for value in (1, 2, 3):
                writer.write(
                    target,
                    {"value": value},
                    validator=lambda item: None,
                    backup_policy=backup_policy,
                    backup_kind="settings",
                )
            backups = list(backup_policy.root.glob("settings-*.json"))
            self.assertEqual(len(backups), 2)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"value": 3})


class FileSongRepositoryTests(unittest.TestCase):
    def test_v4_load_is_read_only_and_first_save_backs_up_original(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = root / "songs.json"
            v4 = {
                "version": 4,
                "songs": [{"title": "知足", "status": "active", "tab_files": [], "learned_at": ""}],
            }
            original_bytes = json.dumps(v4, ensure_ascii=False, indent=2).encode("utf-8")
            path.write_bytes(original_bytes)
            repository = FileSongRepository(path, policy(root))

            snapshot = repository.load()
            self.assertEqual(path.read_bytes(), original_bytes)
            self.assertTrue(snapshot.value.songs[0].id.startswith("song_"))

            saved = repository.save(snapshot.value, expected_revision=snapshot.revision)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["version"], 5)
            backups = list((root / "backups").glob("songs-*.json"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), original_bytes)
            self.assertNotEqual(saved.revision, snapshot.revision)

    def test_snapshot_is_detached_and_two_instances_are_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            first = FileSongRepository(root / "a" / "songs.json", policy(root / "a"))
            second = FileSongRepository(root / "b" / "songs.json", policy(root / "b"))
            first_saved = first.save(
                SongLibrary([Song(title="A")]), expected_revision="missing",
            )
            second.save(SongLibrary([Song(title="B")]), expected_revision="missing")

            first_saved.value.songs[0].title = "锁外修改"
            self.assertEqual(first.load().value.songs[0].title, "A")
            self.assertEqual(second.load().value.songs[0].title, "B")
            first.close()
            self.assertEqual(second.load().value.songs[0].title, "B")

    def test_concurrent_same_revision_exactly_one_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repository = FileSongRepository(root / "songs.json", policy(root))
            initial = repository.save(
                SongLibrary([Song(title="初始")]), expected_revision="missing",
            )
            barrier = threading.Barrier(3)
            outcomes: list[str] = []
            outcome_lock = threading.Lock()

            def worker(title: str) -> None:
                candidate = copy.deepcopy(initial.value)
                candidate.songs[0].title = title
                barrier.wait()
                try:
                    repository.save(candidate, expected_revision=initial.revision)
                    result = "saved"
                except RepositoryConflict:
                    result = "conflict"
                with outcome_lock:
                    outcomes.append(result)

            threads = [threading.Thread(target=worker, args=(title,)) for title in ("甲", "乙")]
            for thread in threads:
                thread.start()
            barrier.wait()
            for thread in threads:
                thread.join(timeout=5)
            self.assertEqual(sorted(outcomes), ["conflict", "saved"])
            self.assertIn(repository.load().value.songs[0].title, {"甲", "乙"})

    def test_close_is_idempotent_and_rejects_operations(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repository = FileSongRepository(root / "songs.json", policy(root))
            repository.close()
            repository.close()
            with self.assertRaises(RepositoryClosed):
                repository.load()
            with self.assertRaises(RepositoryClosed):
                repository.save(SongLibrary(), expected_revision=None)


class FileSettingsRepositoryTests(unittest.TestCase):
    def test_defaults_and_unknown_fields_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = root / "settings.json"
            path.write_text(json.dumps({"known": 1, "future_field": {"x": True}}), encoding="utf-8")
            repository = FileSettingsRepository(
                path,
                policy(root),
                defaults={"known": 0, "default_only": "value"},
            )
            loaded = repository.load()
            saved = repository.save({"known": 2}, expected_revision=loaded.revision)
            self.assertEqual(saved.value["known"], 2)
            self.assertEqual(saved.value["default_only"], "value")
            self.assertEqual(saved.value["future_field"], {"x": True})

            saved.value["future_field"]["x"] = False
            self.assertEqual(repository.load().value["future_field"], {"x": True})

    def test_settings_instances_and_close_are_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            first = FileSettingsRepository(root / "a.json", policy(root / "a"))
            second = FileSettingsRepository(root / "b.json", policy(root / "b"))
            first.save({"name": "A"}, expected_revision="missing")
            second.save({"name": "B"}, expected_revision="missing")
            first.close()
            with self.assertRaises(RepositoryClosed):
                first.load()
            self.assertEqual(second.load().value["name"], "B")


if __name__ == "__main__":
    unittest.main(verbosity=2)
