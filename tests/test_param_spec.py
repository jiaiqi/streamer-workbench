"""P2 R4: ParamSpec 契约测试 — 钉死 core 端 / 后端 / 前端共享的形状。

任意一个 layout 改 params() 返回的字段集时，本测试会失败，
提醒同步更新 UI Inspector。
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.layouts import get_layout


REQUIRED_FIELDS = {"key", "label", "kind", "default"}
VALID_KINDS = {"int", "float", "bool", "select", "section_map", "group_order"}
NUMERIC_KINDS = {"int", "float"}
CHOICE_KINDS = {"select"}
MAP_KINDS = {"section_map"}

from core.layouts import REGISTRY  # noqa: E402


class ParamSpecContractTests(unittest.TestCase):
    """钉死 ParamSpec 形状 — UI Inspector 据此渲染，破坏后 CI 必挂。"""

    def test_all_layouts_have_valid_params(self):
        """每个 layout 的 params() 都必须返回 ParamSpec 列表。"""
        from core.layouts import REGISTRY
        for lid, plugin in REGISTRY.items():
            with self.subTest(layout=lid):
                specs = plugin.params()
                self.assertIsInstance(specs, list, f"{lid}.params() 不是 list")
                self.assertGreater(len(specs), 0, f"{lid} 没声明任何 ParamSpec")
                for ps in specs:
                    self.assertIsInstance(ps.key, str, f"{lid}: key 必须是 str")
                    self.assertIsInstance(ps.label, str, f"{lid}: label 必须是 str")

    def test_keys_unique_within_layout(self):
        for lid, plugin in REGISTRY.items():
            with self.subTest(layout=lid):
                keys = [ps.key for ps in plugin.params()]
                self.assertEqual(len(keys), len(set(keys)),
                                 f"{lid}: ParamSpec.key 有重复 {keys}")

    def test_required_fields_present(self):
        from core.layouts import REGISTRY
        for lid, plugin in REGISTRY.items():
            with self.subTest(layout=lid):
                for ps in plugin.params():
                    self.assertTrue(REQUIRED_FIELDS.issubset(ps.__dict__.keys()),
                                    f"{lid}/{ps.key} 缺必填字段")

    def test_kind_is_valid(self):
        from core.layouts import REGISTRY
        for lid, plugin in REGISTRY.items():
            with self.subTest(layout=lid):
                for ps in plugin.params():
                    self.assertIn(ps.kind, VALID_KINDS,
                                  f"{lid}/{ps.key}: kind={ps.kind!r} 非法")

    def test_numeric_kinds_have_min_max(self):
        from core.layouts import REGISTRY
        for lid, plugin in REGISTRY.items():
            with self.subTest(layout=lid):
                for ps in plugin.params():
                    if ps.kind in NUMERIC_KINDS:
                        self.assertIsNotNone(ps.min,
                            f"{lid}/{ps.key}: {ps.kind} 必须有 min")
                        self.assertIsNotNone(ps.max,
                            f"{lid}/{ps.key}: {ps.kind} 必须有 max")
                        self.assertLess(ps.min, ps.max,
                            f"{lid}/{ps.key}: min 必须 < max")

    def test_select_kind_has_choices(self):
        from core.layouts import REGISTRY
        for lid, plugin in REGISTRY.items():
            with self.subTest(layout=lid):
                for ps in plugin.params():
                    if ps.kind in CHOICE_KINDS:
                        self.assertIsNotNone(ps.choices,
                            f"{lid}/{ps.key}: select 必须有 choices")
                        self.assertGreater(len(ps.choices), 0,
                            f"{lid}/{ps.key}: choices 不能为空")

    def test_section_map_default_is_dict(self):
        from core.layouts import REGISTRY
        for lid, plugin in REGISTRY.items():
            with self.subTest(layout=lid):
                for ps in plugin.params():
                    if ps.kind in MAP_KINDS:
                        self.assertIsInstance(ps.default, dict,
                            f"{lid}/{ps.key}: section_map default 必须是 dict")
                        self.assertIsNotNone(ps.section_axis,
                            f"{lid}/{ps.key}: section_map 必须声明 section_axis")

    def test_group_field_is_string(self):
        from core.layouts import REGISTRY
        for lid, plugin in REGISTRY.items():
            with self.subTest(layout=lid):
                for ps in plugin.params():
                    self.assertIsInstance(ps.group, str,
                        f"{lid}/{ps.key}: group 必须是 str")

    def test_grid_wrap_specific_params(self):
        """grid-wrap 必须保留这 4 个参数（兼容性 — 16 张金标准依赖）"""
        ps = {p.key: p for p in get_layout("grid-wrap").params()}
        for key, default in [("margin", 58), ("font_song", 36),
                             ("row_h", 44), ("sec_gap", 26)]:
            with self.subTest(key=key):
                self.assertIn(key, ps, f"grid-wrap 缺 {key}")
                self.assertEqual(ps[key].default, default,
                                 f"grid-wrap {key} 默认值变了")
                self.assertEqual(ps[key].kind, "int",
                                 f"grid-wrap {key} kind 不是 int")

    def test_magazine_flow_section_map_param(self):
        """magazine-flow 必须暴露每分组栏数 section_map 参数（用户需求）。"""
        ps = {p.key: p for p in get_layout("magazine-flow").params()}
        self.assertIn("columns_per_section", ps)
        spec = ps["columns_per_section"]
        self.assertEqual(spec.kind, "section_map")
        self.assertEqual(spec.section_axis, "chars")
        # 默认必须覆盖 7 个字数分组 + 其他
        for k in ("一字", "二字", "三字", "四字", "五字", "六字", "长歌名", "其他"):
            with self.subTest(group=k):
                self.assertIn(k, spec.default, f"section_map 默认缺 {k}")


if __name__ == "__main__":
    unittest.main()
