"""歌曲库数据层。

Song 模型带元数据；SongLibrary 提供查重/速查/过滤 active。
2026-07-25 状态模型从四态（mastered/learning/wishlist/archived）简化为两态：
  - active（已会，上海报）
  - draft（未会/待学，不上海报）
简化理由：个人单机工具不需要 wishlist/archived 的精细区分；
增加状态复杂度应在有真实用户行为数据后再做。
"""
import json
import os
import shutil
import tempfile
import unicodedata
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import ClassVar, List, Optional


def new_song_id() -> str:
    """为迁移后的新歌生成无业务含义的不可变 ID。"""
    return f"song_{uuid.uuid4().hex}"


def legacy_song_id(title: str) -> str:
    """为 v4 旧歌名生成确定性 ID；只在迁移/内置种子数据中使用。"""
    normalized = unicodedata.normalize("NFC", title or "").strip()
    value = uuid.uuid5(uuid.NAMESPACE_URL, f"streamer-workbench:song:{normalized}")
    return f"song_{value.hex}"


@dataclass
class Song:
    title: str
    id: str = field(default_factory=new_song_id)
    artists: List[str] = field(default_factory=list)
    lyricist: str = ""
    composer: str = ""
    key: str = ""
    capo: Optional[int] = None   # None=未填；0=不夹变调夹（v1→v2 迁移：0→None）
    # R9.4 个人 Capo 库：同一首歌在不同嗓音/状态下可用不同 Capo
    capo_options: List[int] = field(default_factory=list)  # 可选 Capo 列表（去重 + 排序），如 [0, 2, 4]
    capo_default: int = 0  # 习惯 Capo（= capo 字段值；R9.4 之前取 capo，R9.4 之后取 capo_default）
    difficulty: str = ""
    tabs: str = ""
    status: str = "active"     # active（已会，上海报）/ draft（未会，不上海报）
    tags: List[str] = field(default_factory=list)
    pinyin: str = ""
    added_at: str = ""
    notes: str = ""
    learned_at: str = ""         # 学会日期（song_learned 事件时回填；旧 active 歌曲留空）
    # R9.6 软删除：ISO datetime；空字符串 = 未删；30 天后真删（见 cleanup_expired）
    deleted_at: str = ""
    tab_files: List[str] = field(default_factory=list)  # 曲谱文件相对路径（data/tabs/ 下）
    # 分类归属（1=一字..6=六字, 7=长歌名/英文），对应旧脚本 8 个列表的 section。
    # 分组规则（2026-07-25 定案）：
    #   1. 优先用 section 标记（从旧脚本手工分组迁移，保证与金标准一致；
    #      例「恋爱ing」5字但旧脚本在三字列表 → section=3）
    #   2. section 未标记 → 按字数自动分组（中文按 len()，含英文字母归 group 7）
    # 覆盖文件：songs.py 的 YI/ER/SAN/.../LONG_CN 列表维护全部 section 标记。
    section: Optional[int] = None
    # R8 弹唱：歌词（双通道：LRC 带时间戳 / 纯文本兜底；v8.0 默认空）
    lyrics_lrc: str = ""              # LRC 格式 [mm:ss.xx] 歌词
    lyrics_plain: str = ""            # 无时间戳纯文本（无 LRC 时按行均分）
    # R8 弹唱：音频（本地优先，v8.0 默认空；v8.1 加上传 + 播放）
    audio_vocal_path: str = ""        # 原声 data/audio/{song_id}/vocal.{mp3|m4a|ogg|wav}
    audio_instrumental_path: str = "" # 伴奏 data/audio/{song_id}/instrumental.{...}
    audio_duration_ms: int = 0        # 主音频时长缓存（避免每次解码）


@dataclass
class SongLibrary:
    songs: List[Song] = field(default_factory=list)

    def active(self) -> List[Song]:
        """返回所有会上海报的歌曲（status=active）。"""
        return [s for s in self.songs if s.status == "active"]

    def mastered(self) -> List[Song]:
        """兼容旧名：等于 active()。"""
        return self.active()

    def search(self, query: str) -> Optional[Song]:
        """按 title 精确/模糊匹配，返回首个命中；直播速查用。"""
        q = query.strip()
        for s in self.songs:
            if s.title == q:
                return s
        for s in self.songs:
            if q in s.title:
                return s
        return None

    def add(self, song: Song) -> bool:
        """查重：title 或不可变 id 冲突则拦截，返回 False。"""
        if any(s.title == song.title or s.id == song.id for s in self.songs):
            return False
        self.songs.append(song)
        return True

    def mark_active(self, title: str) -> bool:
        """将歌曲状态从 draft 改为 active（一键「学会了」）。返回是否成功找到。"""
        for s in self.songs:
            if s.title == title:
                s.status = "active"
                return True
        return False

    def mark_active_by_id(self, song_id: str) -> bool:
        """按不可变 ID 将歌曲标记为 active。"""
        song = self.get_by_id(song_id)
        if song is None:
            return False
        song.status = "active"
        return True

    def mark_draft(self, title: str) -> bool:
        """将歌曲状态从 active 改为 draft（「标回未会」，下海报）。返回是否成功找到。"""
        for s in self.songs:
            if s.title == title:
                s.status = "draft"
                return True
        return False

    def mark_draft_by_id(self, song_id: str) -> bool:
        """按不可变 ID 将歌曲标记为 draft。"""
        song = self.get_by_id(song_id)
        if song is None:
            return False
        song.status = "draft"
        return True

    def get(self, title: str) -> Optional[Song]:
        """按歌名精确查找，未找到返回 None。"""
        for s in self.songs:
            if s.title == title:
                return s
        return None

    def get_by_id(self, song_id: str) -> Optional[Song]:
        """按不可变 ID 精确查找，未找到返回 None。"""
        for s in self.songs:
            if s.id == song_id:
                return s
        return None

    # 允许编辑的字段（status 走 mark_active/mark_draft；id 不可编辑，title 是显示字段）
    EDITABLE_FIELDS: ClassVar[tuple] = (
        "title", "artists", "lyricist", "composer", "key", "capo",
        # R9.4 个人 Capo 库字段
        "capo_options", "capo_default",
        "difficulty", "tabs", "tags", "pinyin", "notes", "section",
        # R8 弹唱字段：可编辑（前端编辑弹窗 + 音频上传后端会写 audio_*_path）
        "lyrics_lrc", "lyrics_plain",
        "audio_vocal_path", "audio_instrumental_path", "audio_duration_ms",
    )

    def update(self, title: str, fields: dict) -> bool:
        """编辑歌曲信息。title 定位歌曲，fields 为要修改的字段子集。

        title 本身也可通过 fields["title"] 改名（会查重）。
        返回是否成功找到并更新。
        """
        song = self.get(title)
        return self._update_song(song, fields)

    def update_by_id(self, song_id: str, fields: dict) -> bool:
        """按不可变 ID 更新歌曲；改名不会改变关联身份。"""
        song = self.get_by_id(song_id)
        return self._update_song(song, fields)

    def _update_song(self, song: Optional[Song], fields: dict) -> bool:
        """更新已解析的歌曲对象，供 ID 主接口和 title 兼容层共用。"""
        if song is None:
            return False
        new_title = fields.get("title")
        if new_title and new_title != song.title and self.get(new_title) is not None:
            raise ValueError(f"改名失败：「{new_title}」已存在")
        for k, v in fields.items():
            if k in self.EDITABLE_FIELDS:
                setattr(song, k, v)
        return True

    def remove(self, title: str) -> bool:
        """物理删除歌曲。R9.6 后推荐用 soft_delete（保留 30 天可恢复）。"""
        for i, s in enumerate(self.songs):
            if s.title == title:
                self.songs.pop(i)
                return True
        return False

    def remove_by_id(self, song_id: str) -> bool:
        """按不可变 ID 物理删除。R9.6 后推荐用 soft_delete_by_id。"""
        for i, song in enumerate(self.songs):
            if song.id == song_id:
                self.songs.pop(i)
                return True
        return False

    # ---- R9.6 软删除 ----

    def soft_delete_by_id(self, song_id: str, deleted_at: str) -> bool:
        """按不可变 ID 软删除：设置 deleted_at；列表 API 默认排除。
        已删除的歌曲再调一次相当于刷新 deleted_at。
        """
        for s in self.songs:
            if s.id == song_id:
                s.deleted_at = deleted_at
                return True
        return False

    def restore_by_id(self, song_id: str) -> bool:
        """恢复软删除的歌曲（清空 deleted_at）。"""
        for s in self.songs:
            if s.id == song_id:
                s.deleted_at = ""
                return True
        return False

    def purge_by_id(self, song_id: str) -> bool:
        """真删（不可恢复）。"""
        for i, s in enumerate(self.songs):
            if s.id == song_id:
                self.songs.pop(i)
                return True
        return False

    def cleanup_expired(self, days: int = 30, now_iso: Optional[str] = None) -> int:
        """清理超过 days 天的软删除歌曲（真删）。返回清理条数。
        now_iso 形如 '2026-08-02T12:00:00Z'，用于测试注入。
        """
        from datetime import datetime, timedelta, timezone
        if now_iso is None:
            now = datetime.now(timezone.utc)
        else:
            now = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
        cutoff = now - timedelta(days=days)
        before = len(self.songs)
        self.songs = [
            s for s in self.songs
            if not s.deleted_at
            or datetime.fromisoformat(s.deleted_at.replace("Z", "+00:00")) > cutoff
        ]
        return before - len(self.songs)

    def count_active(self) -> int:
        return sum(1 for s in self.songs if s.status == "active" and not s.deleted_at)

    def count_draft(self) -> int:
        return sum(1 for s in self.songs if s.status == "draft" and not s.deleted_at)

    # ---- JSON 持久化 ----
    CURRENT_VERSION: ClassVar[int] = 8

    @staticmethod
    def _migrate_v1_to_v2(data: dict) -> dict:
        """v1→v2：capo 从 int(0=未填) 改为 Optional[int]（0→None）。"""
        for item in data.get("songs", []):
            if item.get("capo") == 0:
                item["capo"] = None
        return data

    @staticmethod
    def _migrate_v2_to_v3(data: dict) -> dict:
        """v2→v3：回填空 pinyin（拼音首字母是歌曲库搜索索引，旧数据全为空）。

        手工改过的非空 pinyin 保留不动。
        """
        for item in data.get("songs", []):
            if not item.get("pinyin") and item.get("title"):
                item["pinyin"] = pinyin_initials(item["title"])
        return data

    @staticmethod
    def _migrate_v3_to_v4(data: dict) -> dict:
        """v3→v4：补 learned_at（学会日期）与 tab_files（曲谱附件）字段默认值。

        旧 active 歌曲 learned_at 留空（统计学习周期时不参与均值，见
        design/roadmap-data-stats.md 第 8 节口径）。
        """
        for item in data.get("songs", []):
            item.setdefault("learned_at", "")
            item.setdefault("tab_files", [])
        return data

    @staticmethod
    def _migrate_v4_to_v5(data: dict) -> dict:
        """v4→v5：为每首歌曲补确定性、不可变的 Song.id。"""
        for item in data.get("songs", []):
            if not item.get("id"):
                item["id"] = legacy_song_id(item.get("title", ""))
        return data

    @staticmethod
    def _migrate_v5_to_v6(data: dict) -> dict:
        """v5→v6：R8 弹唱字段增量。

        所有 R8 字段都有 dataclass 默认值（空字符串 / 0），缺失时 setdefault
        填充；显式 None 视作缺省并清空（防御 dirty data）。
        """
        for item in data.get("songs", []):
            item.setdefault("lyrics_lrc", "")
            item.setdefault("lyrics_plain", "")
            item.setdefault("audio_vocal_path", "")
            item.setdefault("audio_instrumental_path", "")
            item.setdefault("audio_duration_ms", 0)
            # 防御：None / 非字符串 / 负数 → 默认值
            if not isinstance(item.get("lyrics_lrc"), str):
                item["lyrics_lrc"] = ""
            if not isinstance(item.get("lyrics_plain"), str):
                item["lyrics_plain"] = ""
            if not isinstance(item.get("audio_vocal_path"), str):
                item["audio_vocal_path"] = ""
            if not isinstance(item.get("audio_instrumental_path"), str):
                item["audio_instrumental_path"] = ""
            if not isinstance(item.get("audio_duration_ms"), int) or item["audio_duration_ms"] < 0:
                item["audio_duration_ms"] = 0
        return data

    @staticmethod
    def _migrate_v6_to_v7(data: dict) -> dict:
        """v6→v7：R9.4 个人 Capo 库字段增量。

        capo_options: list[int] 默认 []
        capo_default: int 默认取 capo 字段值（None→0）
        """
        for item in data.get("songs", []):
            item.setdefault("capo_options", [])
            item.setdefault("capo_default", item.get("capo") or 0)
            # 防御：capo_options 不是 list[int] → 清空
            opts = item.get("capo_options")
            if not isinstance(opts, list):
                item["capo_options"] = []
            else:
                # 过滤：保留 0-12 整数，去重，排序
                clean = sorted({int(x) for x in opts if isinstance(x, int) and 0 <= x <= 12})
                item["capo_options"] = clean
            # 防御：capo_default 不是 0-12 int → 用 capo 字段
            default = item.get("capo_default")
            if not isinstance(default, int) or default < 0 or default > 12:
                item["capo_default"] = item.get("capo") or 0
        return data

    @staticmethod
    def _migrate_v7_to_v8(data: dict) -> dict:
        """v7→v8：R9.6 软删除字段增量（deleted_at）。"""
        for item in data.get("songs", []):
            item.setdefault("deleted_at", "")
            if not isinstance(item["deleted_at"], str):
                item["deleted_at"] = ""
        return data

    @staticmethod
    def _validate_v5(data: dict) -> dict:
        """拒绝空身份、重复身份和重复歌名，避免带病写入 v5。

        2026-07-30 加固: section 必须在 1..7 区间 (None/0/>=8 都拒绝)
        以保护下游分类与分桶 (LibraryView 「未分类」桶/grid-wrap categorize/magazine-flow
        analyze 都依赖合法 section)。
        """
        ids = set()
        titles = set()
        for index, item in enumerate(data.get("songs", [])):
            song_id = item.get("id")
            title = item.get("title")
            if not isinstance(song_id, str) or not song_id.strip():
                raise ValueError(f"第 {index + 1} 首歌曲缺少有效 id")
            if not isinstance(title, str) or not title.strip():
                raise ValueError(f"第 {index + 1} 首歌曲缺少有效 title")
            if song_id in ids:
                raise ValueError(f"歌曲 id 重复：{song_id}")
            if title in titles:
                raise ValueError(f"歌曲 title 重复：{title}")
            # section 校验 (2026-07-30 加固):
            # - None 是合法值, 与 Song.section: Optional[int] = None 默认对齐
            # - 整数必须 1..7 (与 grid-wrap/magazine-flow _group 索引与金标准一致)
            sec = item.get("section")
            if sec is not None and (not isinstance(sec, int) or sec < 1 or sec > 7):
                raise ValueError(
                    f"第 {index + 1} 首歌曲 section 非法 ({sec!r}); "
                    "必须是 None 或 1..7 的整数"
                )
            ids.add(song_id)
            titles.add(title)
        return data

    MIGRATIONS: ClassVar[dict] = {}  # {from_version: migrate_fn(data) -> data}，在类定义后注册

    @classmethod
    def _migrate(cls, data: dict) -> dict:
        """版本迁移：从数据版本号迭代到 CURRENT_VERSION。"""
        v = data.get("version", 1)
        if v > cls.CURRENT_VERSION:
            raise ValueError(f"歌曲库版本 v{v} 高于当前支持的 v{cls.CURRENT_VERSION}")
        while v < cls.CURRENT_VERSION:
            migrate_fn = cls.MIGRATIONS.get(v)
            if migrate_fn is None:
                raise ValueError(f"缺少版本迁移函数：v{v} → v{v+1}")
            data = migrate_fn(data)
            v += 1
            data["version"] = v
        return cls._validate_v5(data)

    @classmethod
    def load_from_json(cls, path: str) -> "SongLibrary":
        """从 JSON 文件加载歌曲库。文件不存在时返回空库。"""
        if not os.path.isfile(path):
            return cls()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 版本迁移
        data = cls._migrate(data)
        # Section 补全 (2026-07-30): 迁移后仍然 None 的按字数自动分类
        for item in data.get("songs", []):
            if item.get("section") is not None:
                continue
            title = item.get("title", "")
            if any(c.isascii() and c.isalpha() for c in title):
                item["section"] = 7
            else:
                n = len(title.strip())
                item["section"] = n if 1 <= n <= 6 else 7
        songs = [Song(**{k: v for k, v in item.items() if k in Song.__dataclass_fields__})
                 for item in data.get("songs", [])]
        return cls(songs=songs)

    def save(self, path: str, backup_dir: str = None, backup_count: int = 20):
        """原子写入 JSON 文件（先写临时文件再 rename）。

        若提供 backup_dir，写入前把现有文件备份到该目录（时间戳命名），
        保留最近 backup_count 份。
        """
        # 1. 备份现有文件
        if backup_dir and os.path.isfile(path):
            os.makedirs(backup_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(backup_dir, f"songs_{ts}.json")
            shutil.copy2(path, backup_path)
            # 清理旧备份
            backups = sorted(
                (os.path.join(backup_dir, f) for f in os.listdir(backup_dir)
                 if f.startswith("songs_") and f.endswith(".json")),
                key=os.path.getmtime
            )
            for old in backups[:-backup_count]:
                os.unlink(old)

        # 2. 原子写新文件
        payload = {"version": self.CURRENT_VERSION, "songs": [asdict(s) for s in self.songs]}
        self._validate_v5(payload)
        dir_name = os.path.dirname(path)
        os.makedirs(dir_name, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)
        except BaseException:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise


# 注册版本迁移链（类外注册，避免类体内方法引用顺序问题）
SongLibrary.MIGRATIONS.update({1: SongLibrary._migrate_v1_to_v2, 2: SongLibrary._migrate_v2_to_v3,
                               3: SongLibrary._migrate_v3_to_v4, 4: SongLibrary._migrate_v4_to_v5,
                               5: SongLibrary._migrate_v5_to_v6, 6: SongLibrary._migrate_v6_to_v7,
                               7: SongLibrary._migrate_v7_to_v8})


def pinyin_initials(title: str) -> str:
    """生成拼音首字母（如「知足」→「zz」）。

    多音字以 pypinyin 默认读音为准；不准时可在编辑界面手工覆盖
    Song.pinyin 字段（编辑时不回填空值即保留手工值）。
    """
    from pypinyin import lazy_pinyin, Style
    return "".join(lazy_pinyin(title, style=Style.FIRST_LETTER))


# ---- 内置数据（来自 歌单-排版一\build_playlist.py 的 8 个列表）----
YI = ["枫", "耿"]
ER = ["江南", "当你", "心墙", "知足", "倔强", "温柔", "红豆", "如愿", "传奇", "成都", "十年", "晴天", "花海", "安静", "稻香", "搁浅", "彩虹", "退后", "晚婚", "再见", "偏爱", "青柠", "怎样", "画心", "雨爱", "鸽子", "年轮", "抽离", "夜车", "情话", "成全", "白羊", "泪桥", "童话", "落霜", "遇见"]
SAN = ["坏女孩", "他的猫", "小恋曲", "太聪明", "狮子座", "最天使", "老中医", "告诉他", "恋爱ing", "程艾影", "爱一点", "他的爱", "有点甜", "我想念", "小星星", "吵架歌", "黑眼圈", "天黑黑", "第一天", "凑热闹", "盗将行", "明明就", "龙卷风", "七里香", "园游会", "甜甜的", "简单爱", "千年泪", "樱花草", "下一秒", "小幸运", "那些年", "下雨天", "甜不辣", "好想你", "哈哈哈", "我知道", "恶作剧", "小情歌", "晚安喵", "勇敢爱", "大舌头", "吉他手"]
SI = ["后会无期", "忽然之间", "匆匆那年", "阴天快乐", "我们的爱", "依然爱你", "一笑倾城", "专属味道", "万有引力", "我怀念的", "开始懂了", "等你下课", "专属天使", "烟火为聘", "那么骄傲", "时间煮雨", "最后一页", "为你写诗", "寂寞烟火", "云烟成雨", "夏天的风", "我好想你", "如果可以", "可不可以", "多喜欢你", "不是故意", "修炼爱情", "会飞的贼", "荒唐的羊", "爱丫爱丫", "有何不可", "无人之岛", "半句再见", "晴天和猫", "几分之几", "小步舞曲", "山高路远", "六月的雨", "好久不见", "牛仔很忙", "豆浆油条"]
WU = ["背对背拥抱", "客官不可以", "私奔到月球", "如果没有你", "当爱在靠近", "最长的电影", "东京不太热", "我超喜欢你", "可惜没如果", "旅行的意义", "匿名的好友", "还是会寂寞", "慢慢喜欢你", "外面的世界", "我的歌声里", "心愿便利贴", "突然好想你", "握不住的他", "不想做朋友", "出现又离开", "走在冷风中", "勇气大爆发", "奇妙能力歌"]
LIU = ["99次我爱他", "123我爱你", "321对不起", "七秒钟的记忆", "情人节的夜晚", "离开地球表面", "爱的双重魔力", "遥不可及的你", "蒲公英的约定", "有可能的夜晚", "不分手的恋爱", "说好的幸福呢", "我是你的小狗", "阿拉斯加海湾"]
LONG_EN = ["After 17", "Forever 21", "April Encounter"]
LONG_CN = ["当我唱起这首歌", "远在北方孤独的鬼", "一个人想着一个人", "你就不要想起我", "我喜欢上你时的内心活动", "一个像夏天一个像秋天", "那些你很冒险的梦", "考试什么的都去死吧", "二十岁的某一天", "给我一首歌的时间", "这世界那么多人", "遇见你的时候所有星星都落到我头上", "第57次取消发送", "你被写在我的歌里", "我不愿让你一个人", "刻在我心底的名字"]


def build_default_library(json_path: str = None) -> SongLibrary:
    """构造歌曲库。若提供 json_path 且文件存在则优先从 JSON 加载。"""
    if json_path and os.path.isfile(json_path):
        return SongLibrary.load_from_json(json_path)
    """构造内置库（全部 active）。

    优先从 JSON 加载；无 JSON 时 fallback 到内置列表。
    section 标记对应旧脚本的 8 个分类列表（YI=1..LONG=7），保证分组与
    build_playlist.py 的 compose() 完全一致——旧脚本按列表分组而非按字数
    （例「恋爱ing」是 5 字但属三字列表，故 section=3）。
    """
    section_map = [
        (YI, 1), (ER, 2), (SAN, 3), (SI, 4), (WU, 5), (LIU, 6),
        (LONG_EN, 7), (LONG_CN, 7),
    ]
    songs = []
    for lst, sec in section_map:
        for t in lst:
            songs.append(Song(title=t, id=legacy_song_id(t), status="active", section=sec))
    return SongLibrary(songs=songs)
