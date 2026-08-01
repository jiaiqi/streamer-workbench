"""R8.0 弹唱：音频附件存储层测试（10+ 项）。

覆盖：
- 路径白名单（mp3 / m4a / ogg / wav / webm）
- 大小上限 50MB
- 角色命名（vocal / instrumental）
- 重名自动加 -1/-2 后缀
- 路径穿越防护（../）
- 非法 song_id 抛 ValueError
- delete / exists / list_audio / parse_role_from_filename
"""
from __future__ import annotations

import os
import tempfile
import unittest

from core.audio import (
    ALLOWED_EXT, MAX_FILE_BYTES, AUDIO_ROLES,
    save_audio, delete_audio, audio_exists, list_audio,
    parse_role_from_filename,
)


def _make_song_id() -> str:
    """生成符合 SONG_ID_RE 的合法 song_id。"""
    return f"song_{'a' * 32}"


class TestSaveAudio(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "data")
        os.makedirs(self.root)
        self.song_id = _make_song_id()
        self.addCleanup(self.tmp.cleanup)

    def test_save_vocal_mp3(self):
        data = b"\x00" * 1024  # 1KB
        rel = save_audio(self.root, self.song_id, "vocal", "test.mp3", data)
        self.assertEqual(rel, f"audio/{self.song_id}/vocal.mp3")
        self.assertTrue(os.path.isfile(os.path.join(self.root, rel)))

    def test_save_instrumental_m4a(self):
        data = b"fake-m4a-bytes"
        rel = save_audio(self.root, self.song_id, "instrumental", "song.m4a", data)
        self.assertEqual(rel, f"audio/{self.song_id}/instrumental.m4a")
        # 文件内容一致
        with open(os.path.join(self.root, rel), "rb") as f:
            self.assertEqual(f.read(), data)

    def test_save_renames_on_collision(self):
        # 第一次保存 vocal.mp3
        rel1 = save_audio(self.root, self.song_id, "vocal", "a.mp3", b"1")
        self.assertEqual(rel1, f"audio/{self.song_id}/vocal.mp3")
        # 第二次保存 vocal 应该自动 -1
        rel2 = save_audio(self.root, self.song_id, "vocal", "b.mp3", b"2")
        self.assertEqual(rel2, f"audio/{self.song_id}/vocal-1.mp3")
        # 第三次 vocal → vocal-2
        rel3 = save_audio(self.root, self.song_id, "vocal", "c.mp3", b"3")
        self.assertEqual(rel3, f"audio/{self.song_id}/vocal-2.mp3")

    def test_save_rejects_invalid_role(self):
        with self.assertRaisesRegex(ValueError, "不支持的音频角色"):
            save_audio(self.root, self.song_id, "backing", "x.mp3", b"data")

    def test_save_rejects_invalid_extension(self):
        with self.assertRaisesRegex(ValueError, "不支持的文件类型"):
            save_audio(self.root, self.song_id, "vocal", "x.exe", b"data")
        with self.assertRaisesRegex(ValueError, "不支持的文件类型"):
            save_audio(self.root, self.song_id, "vocal", "x", b"data")  # 无扩展名

    def test_save_rejects_oversize(self):
        huge = b"\x00" * (MAX_FILE_BYTES + 1)
        with self.assertRaisesRegex(ValueError, "超过"):
            save_audio(self.root, self.song_id, "vocal", "x.mp3", huge)

    def test_save_accepts_all_allowed_exts(self):
        for ext in ALLOWED_EXT:
            data = f"fake-{ext}-content".encode()
            rel = save_audio(self.root, self.song_id, "vocal", f"x{ext}", data)
            self.assertTrue(rel.endswith(f"vocal{ext}"))

    def test_save_rejects_invalid_song_id(self):
        with self.assertRaisesRegex(ValueError, "非法 song_id"):
            save_audio(self.root, "bad-id", "vocal", "x.mp3", b"data")
        with self.assertRaisesRegex(ValueError, "非法 song_id"):
            save_audio(self.root, "", "vocal", "x.mp3", b"data")
        with self.assertRaisesRegex(ValueError, "非法 song_id"):
            save_audio(self.root, "../escape", "vocal", "x.mp3", b"data")


class TestDeleteAudio(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "data")
        os.makedirs(self.root)
        self.song_id = _make_song_id()
        self.addCleanup(self.tmp.cleanup)

    def test_delete_existing(self):
        rel = save_audio(self.root, self.song_id, "vocal", "x.mp3", b"1")
        self.assertTrue(delete_audio(self.root, self.song_id, rel))
        self.assertFalse(os.path.isfile(os.path.join(self.root, rel)))

    def test_delete_nonexistent(self):
        result = delete_audio(
            self.root, self.song_id,
            f"audio/{self.song_id}/nonexistent.mp3")
        self.assertFalse(result)

    def test_delete_rejects_path_traversal(self):
        # 相对路径含 .. 段 → 拒绝
        self.assertFalse(delete_audio(
            self.root, self.song_id, f"audio/{self.song_id}/../escape.mp3"))
        self.assertFalse(delete_audio(
            self.root, self.song_id, f"audio/other/{self.song_id}.mp3"))

    def test_delete_rejects_wrong_song_id(self):
        with self.assertRaises(ValueError):
            delete_audio(self.root, "bad-id", "audio/bad-id/x.mp3")


class TestAudioExists(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "data")
        os.makedirs(self.root)
        self.song_id = _make_song_id()
        self.addCleanup(self.tmp.cleanup)

    def test_exists_true(self):
        rel = save_audio(self.root, self.song_id, "vocal", "x.mp3", b"1")
        self.assertTrue(audio_exists(self.root, self.song_id, rel))

    def test_exists_false(self):
        self.assertFalse(audio_exists(
            self.root, self.song_id,
            f"audio/{self.song_id}/nope.mp3"))

    def test_exists_rejects_traversal(self):
        self.assertFalse(audio_exists(
            self.root, self.song_id, "audio/other/x.mp3"))


class TestListAudio(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "data")
        os.makedirs(self.root)
        self.song_id = _make_song_id()
        self.addCleanup(self.tmp.cleanup)

    def test_empty(self):
        self.assertEqual(list_audio(self.root, self.song_id), ())

    def test_returns_sorted(self):
        # 注意：role 命名固定 → vocal.mp3 / instrumental.m4a
        save_audio(self.root, self.song_id, "vocal", "z.mp3", b"1")
        save_audio(self.root, self.song_id, "instrumental", "a.m4a", b"2")
        files = list_audio(self.root, self.song_id)
        self.assertEqual(files, ("instrumental.m4a", "vocal.mp3"))

    def test_invalid_song_id(self):
        with self.assertRaises(ValueError):
            list_audio(self.root, "bad-id")


class TestParseRole(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(parse_role_from_filename("vocal.mp3"), "vocal")
        self.assertEqual(parse_role_from_filename("instrumental.m4a"),
                         "instrumental")

    def test_with_suffix(self):
        # 重名时自动加 -1/-2
        self.assertEqual(parse_role_from_filename("vocal-1.mp3"), "vocal")
        self.assertEqual(parse_role_from_filename("instrumental-2.m4a"),
                         "instrumental")

    def test_unknown(self):
        self.assertIsNone(parse_role_from_filename("backing.mp3"))
        self.assertIsNone(parse_role_from_filename("random.m4a"))
        # vocal-old 也算 vocal（startswith 宽松匹配）— 接受

    def test_edge_cases(self):
        self.assertIsNone(parse_role_from_filename(""))
        self.assertIsNone(parse_role_from_filename(".mp3"))  # 无 base name


if __name__ == "__main__":
    unittest.main()
