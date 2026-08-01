"""R4 Runtime v1 抽象测试。

覆盖：
- DataChannel 枚举 + normalize_channel 防御
- LayoutPlugin.supported_channels 类属性 4 套 layout 各声明一个
- capabilities() 返回值包含 supported_channels 字段
- get_layout 不传 channel 保持向后兼容（仅校验 id）
- get_layout 传 channel 校验；不支持时抛 KeyError
- list_layouts 支持 channel 过滤
- 注册表 4 个 layout 全员
- 4 套 layout 各自 capabilities() 仍返回原 supported_canvas_ids 等字段
  （保证向后兼容 + 不破坏金标准）
"""
from __future__ import annotations

import pytest

from core.layouts import (
    REGISTRY, get_layout, list_layouts,
    CHANNELS, normalize_channel, is_supported,
)
from core.layouts.base import LayoutPlugin
from core.layouts.channel import DataChannel


# ---- DataChannel 枚举 ----

class TestDataChannel:
    def test_three_channels_declared(self):
        assert CHANNELS == ("song_library", "live_session", "learning_report")

    def test_normalize_channel_passes_through_literals(self):
        assert normalize_channel("song_library") == "song_library"
        assert normalize_channel("live_session") == "live_session"
        assert normalize_channel("learning_report") == "learning_report"

    def test_normalize_channel_accepts_object_with_id(self):
        class FakeChannel:
            id = "learning_report"
        assert normalize_channel(FakeChannel()) == "learning_report"

    def test_normalize_channel_rejects_unknown_string(self):
        with pytest.raises(ValueError, match="未知 DataChannel"):
            normalize_channel("future-channel")

    def test_normalize_channel_rejects_empty_string(self):
        with pytest.raises(ValueError, match="未知 DataChannel"):
            normalize_channel("")

    def test_normalize_channel_rejects_none(self):
        with pytest.raises(ValueError, match="未知 DataChannel"):
            normalize_channel(None)

    def test_is_supported(self):
        assert is_supported(("song_library",), "song_library") is True
        assert is_supported(("song_library",), "live_session") is False
        assert is_supported((), "song_library") is False
        # 任意 Iterable 都能工作
        assert is_supported(["live_session", "learning_report"], "learning_report") is True


# ---- 注册表 + 4 套 layout 声明 ----

class TestLayoutRegistry:
    def test_registry_has_four_layouts(self):
        assert set(REGISTRY.keys()) == {
            "grid-wrap", "magazine-flow", "live-set", "learning-report",
        }

    def test_all_layouts_are_LayoutPlugin(self):
        for plugin in REGISTRY.values():
            assert isinstance(plugin, LayoutPlugin)

    def test_grid_wrap_declares_song_library(self):
        assert REGISTRY["grid-wrap"].supported_channels == ("song_library",)

    def test_magazine_flow_declares_song_library(self):
        assert REGISTRY["magazine-flow"].supported_channels == ("song_library",)

    def test_live_set_declares_live_session(self):
        assert REGISTRY["live-set"].supported_channels == ("live_session",)

    def test_learning_report_declares_learning_report(self):
        assert REGISTRY["learning-report"].supported_channels == ("learning_report",)

    def test_each_layout_declares_exactly_one_channel(self):
        """R4 Runtime v1 阶段每个 layout 只支持一个数据通道；
        未来多通道 layout（如 grid-wrap + live-set 复用）才考虑支持 tuple 多选。"""
        for plugin in REGISTRY.values():
            assert len(plugin.supported_channels) == 1, \
                f"{plugin.id} 应只声明 1 个 channel"


# ---- capabilities() 字段 ----

class TestCapabilities:
    def test_all_layouts_capabilities_include_supported_channels(self):
        for lid, plugin in REGISTRY.items():
            caps = plugin.capabilities()
            assert "supported_channels" in caps, f"{lid} 缺 supported_channels"
            assert caps["supported_channels"] == list(plugin.supported_channels)

    def test_grid_wrap_capabilities_unchanged_except_new_field(self):
        """向后兼容：原字段全部保留，只新增 supported_channels。"""
        caps = REGISTRY["grid-wrap"].capabilities()
        assert "supported_canvas_ids" in caps
        assert "supports_auto_pagination" in caps
        assert "supports_manual_pages" in caps
        assert "supports_grouping" in caps
        assert "page_policy_mode" in caps
        assert "max_density" in caps

    def test_live_set_capabilities_unchanged_except_new_field(self):
        caps = REGISTRY["live-set"].capabilities()
        assert "9:20" in caps["supported_canvas_ids"]
        assert caps["page_policy_mode"] == "fixed-1"

    def test_learning_report_capabilities_unchanged_except_new_field(self):
        caps = REGISTRY["learning-report"].capabilities()
        assert caps["page_policy_mode"] == "fixed-1"
        assert caps["supported_channels"] == ["learning_report"]


# ---- get_layout ----

class TestGetLayout:
    def test_get_layout_by_id_only_preserves_legacy_behavior(self):
        """不传 channel = R0-R3 旧行为，仅校验 id 存在；channel 不参与校验。"""
        plugin = get_layout("grid-wrap")
        assert plugin.id == "grid-wrap"
        # 同 id + 传支持 channel：照常返回
        plugin2 = get_layout("grid-wrap", channel="song_library")
        assert plugin2 is plugin

    def test_get_layout_with_supported_channel(self):
        plugin = get_layout("live-set", channel="live_session")
        assert plugin.id == "live-set"

    def test_get_layout_with_unsupported_channel_raises(self):
        with pytest.raises(KeyError, match="不支持数据通道"):
            get_layout("grid-wrap", channel="live_session")
        with pytest.raises(KeyError, match="不支持数据通道"):
            get_layout("live-set", channel="song_library")

    def test_get_layout_unknown_id_raises(self):
        with pytest.raises(KeyError, match="未知排版"):
            get_layout("not-a-layout")

    def test_get_layout_error_message_lists_supported(self):
        with pytest.raises(KeyError) as exc_info:
            get_layout("grid-wrap", channel="learning_report")
        # 错误信息应该提示该 layout 已声明的 channel
        assert "song_library" in str(exc_info.value)


# ---- list_layouts ----

class TestListLayouts:
    def test_list_layouts_all(self):
        rows = list_layouts()
        assert len(rows) == 4
        for row in rows:
            assert {"id", "name", "pages", "supports_avoidance",
                    "supported_channels"} <= set(row.keys())

    def test_list_layouts_filter_by_song_library(self):
        rows = list_layouts(channel="song_library")
        ids = {r["id"] for r in rows}
        assert ids == {"grid-wrap", "magazine-flow"}

    def test_list_layouts_filter_by_live_session(self):
        rows = list_layouts(channel="live_session")
        assert len(rows) == 1
        assert rows[0]["id"] == "live-set"

    def test_list_layouts_filter_by_learning_report(self):
        rows = list_layouts(channel="learning_report")
        assert len(rows) == 1
        assert rows[0]["id"] == "learning-report"

    def test_list_layouts_channel_invalid_raises(self):
        with pytest.raises(ValueError):
            list_layouts(channel="bogus")


# ---- LayoutPlugin 默认行为（向后兼容） ----

class TestLayoutPluginDefault:
    def test_subclass_without_supported_channels_has_empty_tuple(self):
        """未显式覆盖 supported_channels 的子类应保持空 tuple（不破坏旧代码）。"""
        class LegacyPlugin(LayoutPlugin):
            id = "legacy"
            name = "Legacy"
            def params(self): return []
            def categorize(self, library): return []
            def render_page(self, ctx, page, library): return 0

        assert LegacyPlugin.supported_channels == ()
        caps = LegacyPlugin().capabilities()
        assert caps["supported_channels"] == []

    def test_empty_supported_channels_means_unreachable(self):
        """空 tuple 表示 layout 还未声明 channel；is_supported 返回 False。"""
        class UnboundPlugin(LayoutPlugin):
            id = "unbound"
            name = "Unbound"
            supported_channels = ()
            def params(self): return []
            def categorize(self, library): return []
            def render_page(self, ctx, page, library): return 0

        # 私有 unbound layout 不在 REGISTRY，所以 list_layouts 不影响
        rows = list_layouts(channel="song_library")
        assert all(r["id"] != "unbound" for r in rows)
        # is_supported 直接检查：空 tuple 永远 False
        assert is_supported(UnboundPlugin.supported_channels, "song_library") is False
        # capabilities() 也会返回空 list
        assert UnboundPlugin().capabilities()["supported_channels"] == []
