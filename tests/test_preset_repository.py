"""R0.7 FilePresetRepository 跨文件事务与恢复测试。"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.data.presets import Preset, SongQuery
from server.ports.repositories import (
    BackupPolicy,
    RepositoryClosed,
    RepositoryConflict,
    RepositoryCorrupt,
    RepositoryRecoveryRequired,
    RepositoryUnavailable,
)
from server.repositories.atomic_json import MISSING_REVISION
from server.repositories.presets import FilePresetRepository, PresetFaultInjector


SONG_ID = "song_227fe9c4775f51e2a3e414bc78fdf12e"


def backup_policy(root: Path) -> BackupPolicy:
    return BackupPolicy(root / "backups", keep=20)


def make_preset(preset_id: str, name: str, *, is_default: bool = False) -> Preset:
    return Preset(
        id=preset_id,
        name=name,
        created_at="2026-07-29T10:00:00",
        updated_at="2026-07-29T10:00:00",
        is_default=is_default,
        song_query=SongQuery(custom_ids=[SONG_ID]),
        layout_id="grid-wrap",
    )


class FilePresetRepositoryTests(unittest.TestCase):
    def test_crud_rename_duplicate_default_and_delete_are_consistent(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repository = FilePresetRepository(root / "presets", backup_policy(root))
            first = repository.save(make_preset("first", "第一套", is_default=True), expected_revision=MISSING_REVISION)
            first.value.palette_id = "源配色"
            first = repository.save(first.value, expected_revision=first.revision)
            second = repository.save(make_preset("second", "第二套"), expected_revision=MISSING_REVISION)
            second.value.palette_id = "第二套源配色"
            second = repository.save(second.value, expected_revision=second.revision)

            renamed = repository.rename("second", "第二套改名", expected_revision=second.revision)
            self.assertEqual(renamed.value.name, "第二套改名")
            duplicated = repository.duplicate("second", make_preset("copy", "副本"))
            self.assertEqual(duplicated.value.id, "copy")
            self.assertEqual(duplicated.value.song_query.custom_ids, renamed.value.song_query.custom_ids)
            self.assertEqual(duplicated.value.name, "副本")
            self.assertEqual(duplicated.value.palette_id, "第二套源配色")

            listing = repository.list()
            default_listing = repository.set_default("second", expected_revision=listing.revision)
            defaults = [item.id for item in default_listing.value if item.is_default]
            self.assertEqual(defaults, ["second"])
            self.assertFalse(repository.get("first").value.is_default)
            self.assertTrue(repository.get("second").value.is_default)

            self.assertTrue(repository.delete("copy", expected_revision=duplicated.revision))
            self.assertIsNone(repository.get("copy"))
            self.assertFalse(repository.delete("missing", expected_revision=None))
            names = {item.id for item in repository.list().value}
            self.assertEqual(names, {"first", "second"})
            self.assertTrue(any((root / "presets" / ".trash").iterdir()))
            self.assertTrue(any((root / "backups").glob("*.json")))
            self.assertEqual(first.value.id, "first")

    def test_each_crash_phase_recovers_complete_old_or_new(self) -> None:
        expected_new = {
            "before_prepared": False,
            "after_prepared": True,
            "after_items_publish": True,
            "after_manifest_publish": True,
            "after_committed": True,
        }
        for phase, should_be_new in expected_new.items():
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                presets_root = root / "presets"
                base = FilePresetRepository(presets_root, backup_policy(root))
                original = base.save(make_preset("scene", "旧名称"), expected_revision=MISSING_REVISION)
                base.close()

                crashing = FilePresetRepository(
                    presets_root,
                    backup_policy(root),
                    fault_injector=PresetFaultInjector(phase),
                )
                changed = copy.deepcopy(original.value)
                changed.name = "新名称"
                with self.assertRaises(RepositoryUnavailable):
                    crashing.save(changed, expected_revision=original.revision)
                with self.assertRaises(RepositoryRecoveryRequired):
                    crashing.get("scene")
                crashing.close()

                recovered = FilePresetRepository(presets_root, backup_policy(root))
                self.assertEqual(recovered.get("scene").value.name, "新名称" if should_be_new else "旧名称")
                self.assertEqual(recovered.list().value[0].name, "新名称" if should_be_new else "旧名称")
                self.assertFalse(any((presets_root / ".transactions").iterdir()))
                self.assertTrue(recovered.recover().recovered)

    def test_delete_crash_rolls_forward_without_duplicate_trash(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            presets_root = root / "presets"
            base = FilePresetRepository(presets_root, backup_policy(root))
            saved = base.save(make_preset("delete_me", "删除目标"), expected_revision=MISSING_REVISION)
            base.close()
            crashing = FilePresetRepository(
                presets_root,
                backup_policy(root),
                fault_injector=PresetFaultInjector("after_items_publish"),
            )
            with self.assertRaises(RepositoryUnavailable):
                crashing.delete("delete_me", expected_revision=saved.revision)
            crashing.close()

            recovered = FilePresetRepository(presets_root, backup_policy(root))
            self.assertIsNone(recovered.get("delete_me"))
            trash_count = len(list((presets_root / ".trash").iterdir()))
            recovered.recover()
            self.assertEqual(len(list((presets_root / ".trash").iterdir())), trash_count)

    def test_set_default_crash_recovers_all_items_and_manifest_together(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            presets_root = root / "presets"
            base = FilePresetRepository(presets_root, backup_policy(root))
            base.save(make_preset("first", "第一套", is_default=True), expected_revision=MISSING_REVISION)
            base.save(make_preset("second", "第二套"), expected_revision=MISSING_REVISION)
            listing = base.list()
            base.close()

            crashing = FilePresetRepository(
                presets_root,
                backup_policy(root),
                fault_injector=PresetFaultInjector("after_items_publish"),
            )
            with self.assertRaises(RepositoryUnavailable):
                crashing.set_default("second", expected_revision=listing.revision)
            crashing.close()

            recovered = FilePresetRepository(presets_root, backup_policy(root))
            self.assertEqual([item.id for item in recovered.list().value if item.is_default], ["second"])
            self.assertFalse(recovered.get("first").value.is_default)
            self.assertTrue(recovered.get("second").value.is_default)

    def test_same_revision_concurrency_exactly_one_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repository = FilePresetRepository(root / "presets", backup_policy(root))
            initial = repository.save(make_preset("scene", "初始"), expected_revision=MISSING_REVISION)
            barrier = threading.Barrier(3)
            outcomes: list[str] = []
            lock = threading.Lock()

            def worker(name: str) -> None:
                candidate = copy.deepcopy(initial.value)
                candidate.name = name
                barrier.wait()
                try:
                    repository.save(candidate, expected_revision=initial.revision)
                    outcome = "saved"
                except RepositoryConflict:
                    outcome = "conflict"
                with lock:
                    outcomes.append(outcome)

            threads = [threading.Thread(target=worker, args=(name,)) for name in ("甲", "乙")]
            for thread in threads:
                thread.start()
            barrier.wait()
            for thread in threads:
                thread.join(timeout=5)
            self.assertEqual(sorted(outcomes), ["conflict", "saved"])

    def test_invalid_ids_custom_ids_orphans_and_corruption_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            presets_root = root / "presets"
            repository = FilePresetRepository(presets_root, backup_policy(root))
            with self.assertRaises(RepositoryCorrupt):
                repository.save(make_preset("../escape", "非法"), expected_revision=MISSING_REVISION)
            invalid = make_preset("invalid_song", "非法歌曲")
            invalid.song_query.custom_ids = ["知足"]
            with self.assertRaises((RepositoryCorrupt, ValueError)):
                repository.save(invalid, expected_revision=MISSING_REVISION)
            repository.close()

            orphan = presets_root / "orphan"
            orphan.mkdir(parents=True)
            (orphan / "preset.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(RepositoryRecoveryRequired):
                FilePresetRepository(presets_root, backup_policy(root))

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            presets_root = root / "presets"
            presets_root.mkdir()
            (presets_root / "manifest.json").write_text("{broken", encoding="utf-8")
            with self.assertRaises(RepositoryCorrupt):
                FilePresetRepository(presets_root, backup_policy(root))

    def test_instances_are_isolated_and_close_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            first = FilePresetRepository(root / "a", backup_policy(root / "a"))
            second = FilePresetRepository(root / "b", backup_policy(root / "b"))
            first.save(make_preset("first", "A"), expected_revision=MISSING_REVISION)
            second.save(make_preset("second", "B"), expected_revision=MISSING_REVISION)
            first.close()
            first.close()
            with self.assertRaises(RepositoryClosed):
                first.list()
            self.assertEqual(second.list().value[0].name, "B")


if __name__ == "__main__":
    unittest.main(verbosity=2)
