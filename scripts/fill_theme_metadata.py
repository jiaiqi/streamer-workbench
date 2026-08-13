"""给 8 套 theme.json 填 metadata 字段。"""
import json
from pathlib import Path

METADATA = {
    "海洋柔光": {
        "tags": ["海洋", "珊瑚", "柔光", "清新", "青绿", "水彩"],
        "scenes": ["直播", "弹唱", "抒情", "小清新"],
        "mood": "fresh",
        "language_friendly": "all",
        "song_count_range": [10, 50],
    },
    "月夜星河": {
        "tags": ["深蓝", "星空", "夜场", "琥珀", "慢歌", "抒情"],
        "scenes": ["夜场", "弹唱", "慢歌", "抒情", "舞台"],
        "mood": "deep",
        "language_friendly": "all",
        "song_count_range": [10, 40],
    },
    "梦幻海洋": {
        "tags": ["海洋", "水彩", "贝壳", "珊瑚", "浅青", "梦幻", "清透"],
        "scenes": ["直播", "抒情", "慢歌", "小清新"],
        "mood": "fresh",
        "language_friendly": "all",
        "song_count_range": [10, 50],
    },
    "卡通音符": {
        "tags": ["卡通", "手绘", "耳机", "吉他", "奶绿", "软萌"],
        "scenes": ["教学", "儿童", "入门", "短视频", "可爱"],
        "mood": "cute",
        "language_friendly": "cn",
        "song_count_range": [5, 30],
    },
    "奶油玻璃": {
        "tags": ["磨砂", "玻璃", "极简", "通透", "粉光", "低饱和"],
        "scenes": ["直播", "短视频", "抒情", "小清新", "现代"],
        "mood": "elegant",
        "language_friendly": "all",
        "song_count_range": [10, 50],
    },
    "奶油花园": {
        "tags": ["花卉", "水彩", "奶油", "暖调", "治愈", "温柔"],
        "scenes": ["教学", "儿童", "入门", "抒情", "温暖"],
        "mood": "warm",
        "language_friendly": "cn",
        "song_count_range": [5, 30],
    },
    "轻复古唱片": {
        "tags": ["黑胶", "信纸", "米白", "复古", "文艺"],
        "scenes": ["抒情", "慢歌", "文艺", "短视频", "复古"],
        "mood": "retro",
        "language_friendly": "all",
        "song_count_range": [10, 50],
    },
    "青提气泡": {
        "tags": ["青提", "气泡", "淡绿", "清爽", "夏日"],
        "scenes": ["夏", "弹唱", "清新", "小清新", "明亮"],
        "mood": "fresh",
        "language_friendly": "all",
        "song_count_range": [10, 40],
    },
}

for theme_name, meta in METADATA.items():
    p = Path(f"themes/{theme_name}/theme.json")
    d = json.load(open(p))
    d["metadata"] = meta
    json.dump(d, open(p, "w"), ensure_ascii=False, indent=2)
    print(f"✅ {theme_name}: tags={len(meta['tags'])} scenes={len(meta['scenes'])} mood={meta['mood']}")
