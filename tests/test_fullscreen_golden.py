"""M0.2 (蓝图 v0.1) fullscreen-flow 新金标准测试。

策略（与 magazine-flow 一致——没有独立预言机）：
- 不做 pixel diff（避免引擎自举）
- 验证 PNG 文件存在 + manifest 中 sha256 与文件实际一致
- 防场景：image 被替换/损坏/漏图

约束：
- 旧 4 套金标准（grid 16 + magazine 5 + live-set 5 + learning-report 5 = 31/31）不被本测试触碰
- 重生成需用 `tools/generate_fullscreen_golden.py --confirm-baseline`
"""
from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = PROJECT_ROOT / "tests" / "golden_fullscreen"
MANIFEST = GOLDEN_DIR / "manifest.json"


class FullscreenGoldenTests(unittest.TestCase):

    def test_manifest_exists(self):
        self.assertTrue(MANIFEST.exists(), f"manifest 缺失：{MANIFEST}")

    def test_manifest_has_schema_v1(self):
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(data["schema_version"], 1)

    def test_manifest_lists_all_cases(self):
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        # 2 cases × 2 pages = 4 entries
        self.assertGreaterEqual(len(data["entries"]), 4)

    def test_each_entry_file_exists_and_sha256_matches(self):
        """逐项核对：磁盘上的 PNG sha256 与 manifest 记录相同。

        如果想「更新基线」: 运行 tools/generate_fullscreen_golden.py --confirm-baseline
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

    def test_canvas_is_9_20(self):
        """fullscreen-flow 强制 9:20 画布（蓝图 §3.5 全屏长图 1080×2400）。"""
        from PIL import Image as _Image
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        for entry in data["entries"]:
            full = PROJECT_ROOT / entry["path"]
            with _Image.open(full) as img:
                w, h = img.size
                self.assertEqual((w, h), (1080, 2400),
                                 f"{entry['path']} 应为 1080×2400，实际 {w}×{h}")


if __name__ == "__main__":
    unittest.main()
