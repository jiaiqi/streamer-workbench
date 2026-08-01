"""R2.5 live-set 新金标准测试。

策略（与 magazine-flow 一致）：
- 不做 pixel diff（避免引擎自举）
- 验证 PNG 文件存在 + manifest 中 sha256 与文件实际一致
- 5 个 case：空场 / 单曲 / 多场 / 大场次 / 混合状态

约束：
- 旧 tests/golden/ 16 张 grid-wrap 金标准不被本测试触碰
- 旧 tests/golden_magazine/ 6 张 magazine-flow 金标准不被本测试触碰
- 重生成需用 `tools/generate_live_set_golden.py --confirm-baseline`
"""
from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = PROJECT_ROOT / "tests" / "golden_live_set"
MANIFEST = GOLDEN_DIR / "manifest.json"


class LiveSetGoldenTests(unittest.TestCase):

    def test_manifest_exists(self):
        self.assertTrue(MANIFEST.exists(), f"manifest 缺失：{MANIFEST}")

    def test_manifest_has_schema_v1(self):
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(data["schema_version"], 1)

    def test_manifest_lists_five_cases(self):
        """5 个代表性用例：empty / single / multi / large / mixed。"""
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(len(data["entries"]), 5,
                         f"应有 5 张金标准，实际 {len(data['entries'])}")

    def test_each_entry_file_exists_and_sha256_matches(self):
        """逐项核对：磁盘上的 PNG sha256 与 manifest 记录相同。"""
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        missing: list[str] = []
        mismatched: list[tuple[str, str, str]] = []
        for entry in data["entries"]:
            rel = entry["path"]
            full = PROJECT_ROOT / rel
            if not full.exists():
                missing.append(rel)
                continue
            actual = hashlib.sha256(full.read_bytes()).hexdigest()
            if actual != entry["sha256"]:
                mismatched.append((rel, entry["sha256"], actual))
        self.assertEqual(missing, [],
                         f"缺失的金标准 PNG: {missing}")
        self.assertEqual(mismatched, [],
                         f"sha256 不匹配（PNG 内容被改过）：{mismatched}")

    def test_each_png_has_nine_twenty_dim(self):
        """所有金标准 PNG 应该是 1080x2400（9:20 抖音全屏）。"""
        from PIL import Image
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        for entry in data["entries"]:
            full = PROJECT_ROOT / entry["path"]
            with Image.open(full) as img:
                self.assertEqual(img.size, (1080, 2400),
                                 f"{entry['path']} 尺寸不对：{img.size}")

    def test_engine_metadata(self):
        """manifest 标注引擎版本。"""
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertIn("engine", data)
        self.assertEqual(data["engine"], "live-set-r25")


if __name__ == "__main__":
    unittest.main()
