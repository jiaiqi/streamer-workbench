"""P2 R4: magazine-flow 接受 parameters 应用到渲染。

覆盖：
- columns_per_section (section_map): 每分组独立栏数
- collapse_threshold (int): 稀疏桶合并
- columns (select): 顶级栏数 fallback
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.data.songs import Song, SongLibrary
from core.layouts.magazine_flow import (
    AXIS_CHARS, AXIS_NONE, MagazineFlowLayout, _apply_collapse,
    categorize_by_axis,
)


def _lib() -> SongLibrary:
    """构造覆盖各分组的样例曲库。"""
    lib = SongLibrary()
    lib.songs = [
        Song(title="枫", status="active", section=1),                              # 1字
        Song(title="耿", status="active", section=1),                              # 1字
        Song(title="江南", status="active", section=2),                            # 2字
        Song(title="十年", status="active", section=2),                            # 2字
        Song(title="晴天", status="active", section=2),                            # 2字
        Song(title="安静", status="active", section=2),                            # 2字
        Song(title="知足", status="active", section=2),                            # 2字
        Song(title="七里香", status="active", section=3),                          # 3字
        Song(title="小情歌", status="active", section=3),                          # 3字
        Song(title="那些年", status="active", section=4),                          # 4字
        Song(title="小幸运", status="active", section=4),                          # 4字
        Song(title="突然好想你", status="active", section=5),                      # 5字
    ]
    return lib


class CollapseTests(unittest.TestCase):
    """_apply_collapse 纯函数测试。"""

    def test_threshold_zero_no_collapse(self):
        cats = [("一字", ["枫", "耿"]), ("二字", ["江南", "十年", "晴天"])]
        result = _apply_collapse(cats, threshold=0)
        self.assertEqual(result, cats)

    def test_collapse_short_bucket_into_next(self):
        # 一字 2 首 < threshold=3 → 合并到下一个非空桶
        cats = [("一字", ["枫", "耿"]), ("二字", ["江南", "十年", "晴天", "安静", "知足"])]
        result = _apply_collapse(cats, threshold=3)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], "一字+二字")
        self.assertEqual(result[0][1], ["枫", "耿", "江南", "十年", "晴天", "安静", "知足"])

    def test_collapse_skips_when_target_meets_threshold(self):
        # 阈值=3; 一字 2 首 (pending), 二字 5 首 (>=3 → 不合并, 直接成桶),
        # 一字 pending 应该跟下一个非空桶合并 — 但二字 >= 阈值, 还是合并
        # 因为我们逻辑是"pending 一定要并到下一个"
        cats = [("一字", ["枫", "耿"]), ("二字", ["a", "b", "c", "d", "e"])]
        result = _apply_collapse(cats, threshold=3)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], "一字+二字")

    def test_collapse_pending_at_end_kept_as_own_bucket(self):
        # 一字 < 阈值, 但没有下一个非空桶 → 单独保留
        cats = [("二字", ["a", "b", "c", "d", "e"]), ("一字", ["枫"])]
        result = _apply_collapse(cats, threshold=3)
        self.assertEqual(len(result), 2)
        # 二字保持原样, 一字单独成桶
        self.assertEqual(result[0][0], "二字")
        self.assertEqual(result[1][0], "一字")

    def test_collapse_no_change_when_all_meet_threshold(self):
        cats = [("一字", ["a", "b", "c"]), ("二字", ["d", "e", "f"])]
        result = _apply_collapse(cats, threshold=3)
        self.assertEqual(result, cats)


class CategorizeParamsTests(unittest.TestCase):
    """categorize() 接受 parameters 决定元数据。"""

    def test_default_no_collapse_no_per_section_cols(self):
        lib = _lib()
        layout = MagazineFlowLayout()
        pages = layout.categorize(lib, axis=AXIS_CHARS)
        # 默认 collapse=0 → 所有原始桶都在
        all_sections = []
        for p in pages:
            for s in p.sections:
                all_sections.append(s["label"])
        self.assertIn("一字", all_sections)
        self.assertIn("二字", all_sections)
        # 默认每组 columns = 0 (渲染时用顶级 columns)
        for p in pages:
            for s in p.sections:
                self.assertEqual(s["columns"], 0)

    def test_collapse_threshold_applied(self):
        lib = _lib()
        layout = MagazineFlowLayout()
        pages = layout.categorize(lib, axis=AXIS_CHARS, parameters={"collapse_threshold": 3})
        all_labels = [s["label"] for p in pages for s in p.sections]
        # 阈值=3, 一字 2 首 pending → 与下一个非空桶"二字"合并
        # 三字 2 首 pending → 与下一个非空桶"四字"合并
        # 五字 1 首 pending → 末尾, 没有下一个非空桶, 单独成桶
        self.assertIn("一字+二字", all_labels)
        self.assertIn("三字+四字", all_labels)
        self.assertIn("五字", all_labels)
        # "二字" 不再单独出现 (已与"一字"合并)
        self.assertNotIn("二字", all_labels)

    def test_columns_per_section_metadata(self):
        lib = _lib()
        layout = MagazineFlowLayout()
        pages = layout.categorize(
            lib, axis=AXIS_CHARS,
            parameters={"columns_per_section": {"一字": 1, "二字": 3, "三字": 2}},
        )
        cols_by_label: dict[str, int] = {}
        for p in pages:
            for s in p.sections:
                cols_by_label.setdefault(s["label"], s["columns"])
        self.assertEqual(cols_by_label.get("一字"), 1)
        self.assertEqual(cols_by_label.get("二字"), 3)
        self.assertEqual(cols_by_label.get("三字"), 2)
        # 未指定的桶保持 0 (fallback 到顶级)
        self.assertEqual(cols_by_label.get("四字"), 0)


class RenderParamsTests(unittest.TestCase):
    """render_page 读 ctx.parameters 应用栏数。"""

    def test_render_with_parameters_runs(self):
        """集成 smoke：传入 parameters 不抛错，y 进度合理推进。"""
        from core.context import DrawContext
        from core.spec import get_canvas_spec
        from core.themes.model import Style
        from PIL import Image, ImageDraw, ImageFont

        lib = _lib()
        spec = get_canvas_spec("抖音全屏 9:20", avoid=False)
        img = Image.new("RGB", (spec.width, spec.height), "white")
        d = ImageDraw.Draw(img)
        font = ImageFont.truetype("fonts/MaokenAssortedSans.ttf", 36)
        font_label = ImageFont.truetype("fonts/MaokenAssortedSans.ttf", 24)
        # Style 必填字段最小集（颜色是 RGB/RGBA tuple）
        style = Style(
            text=(17, 17, 17),
            label=(17, 17, 17),
            pill=(238, 238, 238, 255),
            line=(204, 204, 204),
            mist=(136, 136, 136, 255),
        )

        # 验证 columns_per_section 改变栏数 — 用空 page
        from core.layouts import REGISTRY
        layout = REGISTRY["magazine-flow"]
        ctx = DrawContext(
            draw=d, spec=spec, style=style,
            font_song=font, font_label=font_label,
            parameters={
                "columns_per_section": {"一字": 1, "二字": 3, "三字": 2, "四字": 2},
                "columns": 2,
                "collapse_threshold": 3,
                "show_date": False,
                "margin": 58,
            },
        )
        # 第一页有刊头，恰好能跑通
        y_end = layout.render_page(ctx, page=1, library=lib)
        self.assertGreater(y_end, 0, "render_page 应当推进 y 坐标")


if __name__ == "__main__":
    unittest.main()
