"""P1 R1a.2 样例数据 seed 端到端测试。"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.config import AppConfig
from tests.test_api_contract import _request


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _boot_app(data_root: Path):
    from server.app import create_app
    return create_app(AppConfig(PROJECT_ROOT, mode="test", data_root=data_root))


class SampleSeedApiTests(unittest.TestCase):
    """POST /api/songs/seed-sample 仅在曲库为空时生效。"""

    def test_seed_empty_library_loads_samples(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    status, body, _ = await _request(
                        app, "POST", "/api/songs/seed-sample", None,
                    )
                    assert status == 200, body
                    assert body["ok"] is True
                    assert body["active"] >= 10
                    assert isinstance(body["added"], list)
                    assert len(body["added"]) >= 10

                    # 再调一次：应幂等，不重复
                    status, body2, _ = await _request(
                        app, "POST", "/api/songs/seed-sample", None,
                    )
                    assert status == 200
                    assert body2["added"] == []   # 第二次不增加
        asyncio.run(scenario())

    def test_seed_does_not_overwrite_existing_songs(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    # 先用 sample seed 1 次
                    await _request(app, "POST", "/api/songs/seed-sample", None)
                    # 此时已 active ≥ 10；再调用应幂等
                    status, body, _ = await _request(
                        app, "POST", "/api/songs/seed-sample", None,
                    )
                    assert status == 200
                    assert body["added"] == []
                    assert body["active"] >= 10
        asyncio.run(scenario())

    def test_seed_persists_across_app_restart(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                data_root = Path(raw)
                app1 = _boot_app(data_root)
                async with app1.router.lifespan_context(app1):
                    await _request(app1, "POST", "/api/songs/seed-sample", None)

                # 重启 app
                app2 = _boot_app(data_root)
                async with app2.router.lifespan_context(app2):
                    status, body, _ = await _request(
                        app2, "GET", "/api/songs/list", None,
                    )
                    assert status == 200
                    assert len(body["songs"]) >= 10
        asyncio.run(scenario())


class SampleSeedLibraryTests(unittest.TestCase):
    """领域层 sample_songs.py 单元测试——不依赖 HTTP。"""

    def test_seed_to_non_empty_is_noop(self):
        from core.data.songs import Song, SongLibrary, legacy_song_id
        from core.data.sample_songs import seed_to_library, is_library_empty
        lib = SongLibrary()
        lib.songs.append(
            Song(title="已经有的歌", id=legacy_song_id("已经有的歌")),
        )
        assert not is_library_empty(lib)
        added = seed_to_library(lib)
        assert added == []

    def test_seed_to_empty_loads_known_minimum(self):
        from core.data.songs import SongLibrary
        from core.data.sample_songs import seed_to_library, SAMPLE_SEED
        lib = SongLibrary()
        added = seed_to_library(lib)
        assert len(added) == len(SAMPLE_SEED)
        # 每首都有合法 song_id
        import re
        ID_RE = re.compile(r"^song_[0-9a-f]{32}$")
        for song in added:
            assert ID_RE.match(song.id), song.id
            assert song.status == "active"


if __name__ == "__main__":
    unittest.main()
