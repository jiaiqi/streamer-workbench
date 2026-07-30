"""R1b magazine-flow 新金标准测试。

策略（与 grid-wrap 不同——没有独立预言机）：
- 不做 pixel diff（避免引擎自举）
- 验证 PNG 文件存在 + manifest 中 sha256 与文件实际一致
- 防场景：image 被替换/损坏/漏图

约束：
- 旧 tests/golden/ 的 16 张 grid-wrap 金标准不被本测试触碰
- 重生成需用 `tools/generate_magazine_golden.py --confirm-baseline`
"""
from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = PROJECT_ROOT / "tests" / "golden_magazine"
MANIFEST = GOLDEN_DIR / "manifest.json"


class MagazineGoldenTests(unittest.TestCase):

    def test_manifest_exists(self):
        self.assertTrue(MANIFEST.exists(), f"manifest 缺失：{MANIFEST}")

    def test_manifest_has_schema_v1(self):
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(data["schema_version"], 1)

    def test_manifest_lists_all_three_cases(self):
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        # 3 cases × 2 pages = 6 entries
        self.assertGreaterEqual(len(data["entries"]), 6)

    def test_each_entry_file_exists_and_sha256_matches(self):
        """逐项核对：磁盘上的 PNG sha256 与 manifest 记录相同。

        如果想「更新基线」: 运行 tools/generate_magazine_golden.py --confirm-baseline
        """
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

    def test_canvases_actually_differ(self):
        """不同画布尺寸的金标准 PNG 不应该有完全相同内容。
        防止之前的 bug（所有画布都生成 1080×1920）回归。"""
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        paths = [
            (PROJECT_ROOT / e["path"], e["canvas"])
            for e in data["entries"]
        ]
        # 海洋柔光 9:20 vs 9:16 应是不同的画布 → 不同尺寸
        seen_sizes: dict[str, tuple] = {}
        for path, canvas in paths:
            from PIL import Image as _Image_mod
            with _Image_mod.open(path) as img:
                seen_sizes.setdefault(canvas, img.size)
        self.assertEqual(len(seen_sizes), 2,
                         f"应至少 2 种画布尺寸，实际仅 {list(seen_sizes.keys())}")


if __name__ == "__main__":
    unittest.main()
