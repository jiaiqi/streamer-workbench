"""单元测试：theme loader / Song 模型 / 布局 / 分组规则。

覆盖设计结论 §9.1 要求的主题校验异常路径、Song 模型生命周期、
分组规则（section 标记 + 字数回退）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.themes.loader import load_themes, load_theme
from core.themes.model import Theme
from core.style import Style
from core.data.songs import Song, SongLibrary, build_default_library
from core.layouts import get_layout, list_layouts

THEMES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "themes")


# ═══════ Theme Loader ═══════

def test_load_themes_all_7():
    themes = load_themes(THEMES_DIR)
    assert len(themes) == 7
    assert "海洋柔光" in themes
    assert "青提气泡" in themes

def test_theme_styles_have_5_roles():
    themes = load_themes(THEMES_DIR)
    for name, t in themes.items():
        for page in (1, 2):
            s = t.styles[page]
            assert s.text is not None
            assert s.label is not None
            assert s.pill is not None
            assert s.line is not None
            assert s.mist is not None

def test_theme_backgrounds_exist():
    themes = load_themes(THEMES_DIR)
    for name, t in themes.items():
        for page in (1, 2):
            path = t.background_path(page)
            assert os.path.isfile(path), f"{name} p{page}: {path}"

def test_theme_json_format():
    themes = load_themes(THEMES_DIR)
    for name, t in themes.items():
        assert t.name
        assert t.output_prefix
        assert isinstance(t.backgrounds, dict)
        assert "1" in t.backgrounds
        assert "2" in t.backgrounds
        assert isinstance(t.watermark_fix, bool)

def test_loader_missing_field_detected():
    import json, tempfile
    bad = {"name": "x", "output_prefix": "x", "backgrounds": {"1": "x.png"}}
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(bad, f)
    p = f.name
    f.close()
    try:
        load_theme(p)
        assert False, "Should raise ValueError"
    except (ValueError, KeyError):
        pass
    finally:
        os.unlink(p)


# ═══════ Song Model ═══════

def test_song_default_status_active():
    s = Song(title="x")
    assert s.status == "active"

def test_library_active():
    lib = SongLibrary([
        Song(title="a", status="active"),
        Song(title="b", status="draft"),
        Song(title="c", status="active"),
    ])
    a = lib.active()
    assert len(a) == 2
    assert {s.title for s in a} == {"a", "c"}

def test_library_mastered_compat():
    lib = SongLibrary([
        Song(title="a", status="active"),
        Song(title="b", status="draft"),
    ])
    assert len(lib.mastered()) == len(lib.active())

def test_library_add_duplicate():
    lib = SongLibrary([Song(title="a")])
    assert lib.add(Song(title="a")) is False
    assert lib.add(Song(title="b")) is True

def test_mark_active():
    lib = SongLibrary([Song(title="a", status="draft"), Song(title="b", status="active")])
    assert lib.mark_active("a") is True
    assert lib.mark_active("x") is False
    assert [s.status for s in lib.songs] == ["active", "active"]

def test_mark_draft():
    lib = SongLibrary([Song(title="a", status="active"), Song(title="b", status="draft")])
    assert lib.mark_draft("a") is True
    assert lib.mark_draft("x") is False
    assert [s.status for s in lib.songs] == ["draft", "draft"]

def test_update():
    lib = SongLibrary([Song(title="a"), Song(title="b")])
    assert lib.update("a", {"key": "G", "capo": 2, "tags": ["小甜歌"]}) is True
    s = lib.get("a")
    assert s.key == "G" and s.capo == 2 and s.tags == ["小甜歌"]
    assert lib.update("x", {"key": "C"}) is False

def test_update_rename_dedupe():
    lib = SongLibrary([Song(title="a"), Song(title="b")])
    assert lib.update("a", {"title": "c"}) is True
    assert lib.get("c") is not None and lib.get("a") is None
    try:
        lib.update("b", {"title": "c"})
        assert False, "改名撞车应抛 ValueError"
    except ValueError:
        pass

def test_remove():
    lib = SongLibrary([Song(title="a"), Song(title="b")])
    assert lib.remove("a") is True
    assert lib.remove("x") is False
    assert [s.title for s in lib.songs] == ["b"]

def test_migration_v1_to_v2_capo():
    data = {"version": 1, "songs": [
        {"title": "a", "capo": 0}, {"title": "b", "capo": 3}]}
    out = SongLibrary._migrate(data)
    assert out["songs"][0]["capo"] is None
    assert out["songs"][1]["capo"] == 3

def test_migration_v2_to_v3_pinyin():
    data = {"version": 2, "songs": [
        {"title": "知足", "pinyin": ""},          # 空 → 回填
        {"title": "枫", "pinyin": "custom"},      # 手工非空 → 保留
        {"title": "", "pinyin": ""}]}             # 无标题 → 不炸
    out = SongLibrary._migrate(data)
    assert out["songs"][0]["pinyin"] == "zz"
    assert out["songs"][1]["pinyin"] == "custom"
    assert out["songs"][2]["pinyin"] == ""

def test_migration_chain_v1_to_v3():
    data = {"version": 1, "songs": [{"title": "知足", "capo": 0, "pinyin": ""}]}
    out = SongLibrary._migrate(data)
    assert out["songs"][0]["capo"] is None
    assert out["songs"][0]["pinyin"] == "zz"

def test_pinyin_initials():
    from core.data.songs import pinyin_initials
    assert pinyin_initials("知足") == "zz"
    assert pinyin_initials("枫") == "f"

def test_search():
    lib = SongLibrary([Song(title="a"), Song(title="ab")])
    s = lib.search("a")
    assert s.title == "a"
    assert lib.search("c") is None

def test_count():
    lib = SongLibrary([
        Song(title="a", status="active"),
        Song(title="b", status="draft"),
    ])
    assert lib.count_active() == 1
    assert lib.count_draft() == 1


# ═══════ Layout Registry ═══════

def test_layout_registry():
    ls = list_layouts()
    ids = [l["id"] for l in ls]
    assert "grid-wrap" in ids

def test_get_layout():
    l = get_layout("grid-wrap")
    assert l.id == "grid-wrap"

def test_layout_pages():
    assert get_layout("grid-wrap").pages == 2

def test_get_layout_nonexistent():
    try:
        get_layout("no")
        assert False
    except KeyError:
        pass

def test_layout_params():
    keys = [p.key for p in get_layout("grid-wrap").params()]
    assert "margin" in keys
    assert "font_song" in keys


# ═══════ Grouping Logic ═══════

def test_group_section_override():
    """恋爱ing is 5 chars but section=3 → goes to 三字."""
    lib = SongLibrary([Song(title="恋爱ing", status="active", section=3)])
    from core.layouts.grid_wrap import _group
    g = _group(lib)
    assert "恋爱ing" in g[3]
    assert "恋爱ing" not in g[5]

def test_group_fallback_len():
    lib = SongLibrary([Song(title="枫", status="active")])
    from core.layouts.grid_wrap import _group
    g = _group(lib)
    assert "枫" in g[1]

def test_group_english_to_7():
    lib = SongLibrary([Song(title="Hello", status="active")])
    from core.layouts.grid_wrap import _group
    g = _group(lib)
    assert "Hello" in g[7]

def test_default_library_178():
    lib = build_default_library()
    assert lib.count_active() == 178
    from core.layouts.grid_wrap import _group
    g = _group(lib)
    assert g[1] == ["枫", "耿"]


# ═══════ Runner ═══════

if __name__ == "__main__":
    import traceback
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    p = f = 0
    for t in tests:
        try:
            t()
            print(f"  ✅ {t.__name__}")
            p += 1
        except Exception as e:
            print(f"  ❌ {t.__name__}: {e}")
            traceback.print_exc()
            f += 1
    print(f"\n{p} passed, {f} failed")
    sys.exit(1 if f else 0)
