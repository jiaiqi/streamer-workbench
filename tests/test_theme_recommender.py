"""M3 P3 续: Theme metadata 加载 + 智能推荐算法测试。

覆盖：
- ThemeMetadata 字段（frozen + tuple 强制）
- 8 套 theme.json 加载后 metadata 字段生效
- score_theme 关键词命中 + 场景命中 + mood 命中 + 数量范围
- recommend_themes_all 按分数降序排
- 端点 /api/themes/recommend 集成（manual + poster_id 两种）
- 端点 /api/themes 返回 metadata 字段
"""
from __future__ import annotations

import pytest

from core.themes.recommender import (
    PosterContext,
    ThemeScore,
    score_theme,
    recommend_themes,
    recommend_themes_all,
)
from core.themes.model import ThemeMetadata
from core.themes.loader import load_theme


# ── ThemeMetadata ──

class TestThemeMetadata:
    def test_default_empty(self):
        """v1 兼容：空 ThemeMetadata"""
        m = ThemeMetadata()
        assert m.tags == ()
        assert m.scenes == ()
        assert m.mood == ""
        assert m.language_friendly == "all"
        assert m.song_count_range == (0, 9999)

    def test_explicit_values(self):
        m = ThemeMetadata(
            tags=("海洋", "清新"),
            scenes=("直播", "弹唱"),
            mood="fresh",
            language_friendly="cn",
            song_count_range=(10, 50),
        )
        assert m.tags == ("海洋", "清新")
        assert m.scenes == ("直播", "弹唱")
        assert m.mood == "fresh"
        assert m.song_count_range == (10, 50)

    def test_accepts_list_converts_to_tuple(self):
        """list 输入自动转 tuple（frozen 友好）"""
        m = ThemeMetadata(tags=["a", "b"], scenes=["c"], song_count_range=[5, 30])
        assert isinstance(m.tags, tuple)
        assert isinstance(m.scenes, tuple)
        assert m.song_count_range == (5, 30)

    def test_frozen(self):
        """frozen=True：字段赋值抛错"""
        m = ThemeMetadata(tags=("a",))
        with pytest.raises(Exception):
            m.tags = ("b",)  # type: ignore[misc]


# ── theme.json 加载 metadata ──

class TestThemeJsonMetadata:
    def _load_all(self):
        return [load_theme(f"themes/{n}") for n in
                ["海洋柔光", "月夜星河", "梦幻海洋", "卡通音符",
                 "奶油玻璃", "奶油花园", "轻复古唱片", "青提气泡"]]

    def test_haiyang_rouguang_metadata(self):
        t = load_theme("themes/海洋柔光")
        assert "海洋" in t.metadata.tags
        assert "弹唱" in t.metadata.scenes
        assert t.metadata.mood == "fresh"
        assert t.metadata.song_count_range == (10, 50)

    def test_yueye_xinghe_metadata(self):
        t = load_theme("themes/月夜星河")
        assert "深蓝" in t.metadata.tags
        assert "夜场" in t.metadata.scenes
        assert t.metadata.mood == "deep"
        assert t.metadata.song_count_range == (10, 40)

    def test_katong_yinfu_cn_only(self):
        t = load_theme("themes/卡通音符")
        assert t.metadata.language_friendly == "cn"
        assert t.metadata.mood == "cute"

    def test_all_8_themes_loaded(self):
        themes = self._load_all()
        assert len(themes) == 8
        # 每套都有 tags + scenes + mood
        for t in themes:
            assert len(t.metadata.tags) > 0
            assert len(t.metadata.scenes) > 0
            assert t.metadata.mood != ""


# ── score_theme ──

class TestScoreTheme:
    def _haiyang(self):
        return load_theme("themes/海洋柔光")

    def test_tag_hits(self):
        """关键词命中加分（每命中 +3）"""
        theme = self._haiyang()
        ctx = PosterContext(title="", song_titles=("海洋之歌", "珊瑚"), tags=("青绿",))
        s = score_theme(theme, ctx)
        # 命中 3 个：海洋、珊瑚、青绿
        assert s.tag_hits == 3
        assert s.score == pytest.approx(3 * 3, abs=1.5)

    def test_scene_hits(self):
        """场景命中加分（每命中 +2）"""
        theme = self._haiyang()
        ctx = PosterContext(title="", scene="弹唱")
        s = score_theme(theme, ctx)
        # 海洋柔光 scenes = ("直播", "弹唱", "抒情", "小清新")
        assert s.scene_hits >= 1

    def test_mood_hit(self):
        """mood 匹配 +2"""
        theme = self._haiyang()  # mood="fresh"
        ctx = PosterContext(title="夏日清新小清新")
        s = score_theme(theme, ctx)
        # _normalize_mood("夏日清新小清新") → "fresh"
        assert s.mood_hit is True

    def test_mood_miss(self):
        """mood 不匹配 0 分"""
        theme = self._haiyang()  # mood="fresh"
        ctx = PosterContext(title="")  # 推断不出 mood
        s = score_theme(theme, ctx)
        assert s.mood_hit is False

    def test_count_in_range(self):
        """数量在范围内 +1"""
        theme = self._haiyang()  # (10, 50)
        s = score_theme(theme, PosterContext(song_count=20))
        assert s.count_in_range is True

    def test_count_out_of_range_penalty(self):
        """数量超出范围 -0.5（轻扣）"""
        theme = self._haiyang()  # (10, 50)
        s = score_theme(theme, PosterContext(song_count=5))
        assert s.count_in_range is False
        # 验证 penalty：score 应含 -0.5
        assert s.score == pytest.approx(-0.5, abs=0.01)

    def test_score_serialization(self):
        s = score_theme(self._haiyang(), PosterContext(title="海洋"))
        d = s.to_dict()
        assert d["theme_name"] == "海洋柔光"
        assert isinstance(d["score"], (int, float))
        assert "tag_hits" in d


# ── recommend_themes_all ──

class TestRecommendThemesAll:
    def _all_themes(self):
        return [load_theme(f"themes/{n}") for n in
                ["海洋柔光", "月夜星河", "梦幻海洋", "卡通音符",
                 "奶油玻璃", "奶油花园", "轻复古唱片", "青提气泡"]]

    def test_qingxin_弹唱_recommends_haiyang(self):
        """清新弹唱 → 海洋柔光 / 青提气泡排前（清新 mood + 弹唱场景）"""
        ctx = PosterContext(title="夏日清新", song_titles=("后来",),
                            tags=("弹唱",), scene="弹唱", song_count=20)
        scores = recommend_themes_all(self._all_themes(), ctx)
        # top 3 应该包含 海洋柔光 / 青提气泡 / 梦幻海洋
        top3 = [s.theme_name for s in scores[:3]]
        assert "海洋柔光" in top3
        assert "青提气泡" in top3

    def test_yechang_mange_recommends_yueye(self):
        """夜场慢歌 → 月夜星河排第一（深色 mood + 夜场场景命中）"""
        ctx = PosterContext(title="深夜慢歌", tags=("慢歌",), scene="夜场", song_count=15)
        scores = recommend_themes_all(self._all_themes(), ctx)
        assert scores[0].theme_name == "月夜星河"
        assert scores[0].score > 0

    def test_sort_descending(self):
        """按 score 降序排"""
        ctx = PosterContext(title="夏日清新", scene="弹唱", song_count=20)
        scores = recommend_themes_all(self._all_themes(), ctx)
        for i in range(len(scores) - 1):
            assert scores[i].score >= scores[i + 1].score

    def test_top_n_truncation(self):
        """recommend_themes(top_n=2) 返前 2 个"""
        ctx = PosterContext(title="夏日清新", song_count=20)
        top2 = recommend_themes(self._all_themes(), ctx, top_n=2)
        assert len(top2) == 2


# ── 端点集成 ──

class TestRecommendEndpoint:
    def _make_app(self, tmp):
        from server.app import create_app
        from server.config import AppConfig
        config = AppConfig(
            project_root=__import__("pathlib").Path(".").resolve(),
            mode="test", data_root=__import__("pathlib").Path(tmp),
            host="127.0.0.1",
            allowed_origins=("http://localhost", "http://127.0.0.1"),
        )
        return create_app(config)

    def test_endpoint_manual_query(self):
        """GET /api/themes/recommend?title=...&song_titles=... 端点"""
        from fastapi.testclient import TestClient
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            app = self._make_app(tmp)
            with TestClient(app) as c:
                r = c.get(
                    "/api/themes/recommend?"
                    "title=夏日清新弹唱&song_titles=后来的我们,小幸运"
                    "&tags=清新&scene=弹唱&song_count=20&top_n=3"
                )
                assert r.status_code == 200
                data = r.json()
                assert "recommendations" in data
                assert len(data["recommendations"]) == 3
                # 海洋柔光 应在前 3
                top3 = [r["theme_name"] for r in data["recommendations"]]
                assert "海洋柔光" in top3
                # 上下文回显
                assert data["context"]["title"] == "夏日清新弹唱"
                assert data["context"]["song_count"] == 20
                # themes 字段含 prefix + notes
                assert "themes" in data
                for t in data["themes"]:
                    assert "name" in t
                    assert "prefix" in t

    def test_endpoint_top_n_validation(self):
        """top_n 必须 1-10"""
        from fastapi.testclient import TestClient
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            app = self._make_app(tmp)
            with TestClient(app) as c:
                r = c.get("/api/themes/recommend?top_n=0")
                assert r.status_code == 422
                r = c.get("/api/themes/recommend?top_n=11")
                assert r.status_code == 422

    def test_endpoint_poster_id(self):
        """提供 poster_id → 自动解析"""
        from fastapi.testclient import TestClient
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            app = self._make_app(tmp)
            with TestClient(app) as c:
                # 没 poster_id → graceful
                r = c.get("/api/themes/recommend?poster_id=non-existent-id")
                assert r.status_code == 200
                data = r.json()
                # 推荐应返默认 3 套（无 context）
                assert len(data["recommendations"]) == 3

    def test_endpoint_themes_includes_metadata(self):
        """GET /api/themes 返回 metadata 字段"""
        from fastapi.testclient import TestClient
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            app = self._make_app(tmp)
            with TestClient(app) as c:
                r = c.get("/api/themes")
                assert r.status_code == 200
                data = r.json()
                # 至少 1 套 theme（含 metadata）
                assert len(data) > 0
                for t in data:
                    assert "metadata" in t
                    meta = t["metadata"]
                    assert "tags" in meta
                    assert "scenes" in meta
                    assert "mood" in meta
                    assert "song_count_range" in meta
