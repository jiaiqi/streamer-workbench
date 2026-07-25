"""歌曲库数据层。

Song 模型带元数据；SongLibrary 提供查重/速查/过滤 active。
2026-07-25 状态模型从四态（mastered/learning/wishlist/archived）简化为两态：
  - active（已会，上海报）
  - draft（未会/待学，不上海报）
简化理由：个人单机工具不需要 wishlist/archived 的精细区分；
增加状态复杂度应在有真实用户行为数据后再做。
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Song:
    title: str
    artists: List[str] = field(default_factory=list)
    lyricist: str = ""
    composer: str = ""
    key: str = ""
    capo: int = 0
    difficulty: str = ""
    tabs: str = ""
    status: str = "active"     # active（已会，上海报）/ draft（未会，不上海报）
    tags: List[str] = field(default_factory=list)
    pinyin: str = ""
    added_at: str = ""
    notes: str = ""
    # 分类归属（1=一字..6=六字, 7=长歌名/英文），对应旧脚本 8 个列表的 section。
    # 分组规则（2026-07-25 定案）：
    #   1. 优先用 section 标记（从旧脚本手工分组迁移，保证与金标准一致；
    #      例「恋爱ing」5字但旧脚本在三字列表 → section=3）
    #   2. section 未标记 → 按字数自动分组（中文按 len()，含英文字母归 group 7）
    # 覆盖文件：songs.py 的 YI/ER/SAN/.../LONG_CN 列表维护全部 section 标记。
    section: Optional[int] = None


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
        """查重：title 完全相同则拦截，返回 False。"""
        if any(s.title == song.title for s in self.songs):
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

    def count_active(self) -> int:
        return sum(1 for s in self.songs if s.status == "active")

    def count_draft(self) -> int:
        return sum(1 for s in self.songs if s.status == "draft")


# ---- 内置数据（来自 歌单-排版一\build_playlist.py 的 8 个列表）----
YI = ["枫", "耿"]
ER = ["江南", "当你", "心墙", "知足", "倔强", "温柔", "红豆", "如愿", "传奇", "成都", "十年", "晴天", "花海", "安静", "稻香", "搁浅", "彩虹", "退后", "晚婚", "再见", "偏爱", "青柠", "怎样", "画心", "雨爱", "鸽子", "年轮", "抽离", "夜车", "情话", "成全", "白羊", "泪桥", "童话", "落霜", "遇见"]
SAN = ["坏女孩", "他的猫", "小恋曲", "太聪明", "狮子座", "最天使", "老中医", "告诉他", "恋爱ing", "程艾影", "爱一点", "他的爱", "有点甜", "我想念", "小星星", "吵架歌", "黑眼圈", "天黑黑", "第一天", "凑热闹", "盗将行", "明明就", "龙卷风", "七里香", "园游会", "甜甜的", "简单爱", "千年泪", "樱花草", "下一秒", "小幸运", "那些年", "下雨天", "甜不辣", "好想你", "哈哈哈", "我知道", "恶作剧", "小情歌", "晚安喵", "勇敢爱", "大舌头", "吉他手"]
SI = ["后会无期", "忽然之间", "匆匆那年", "阴天快乐", "我们的爱", "依然爱你", "一笑倾城", "专属味道", "万有引力", "我怀念的", "开始懂了", "等你下课", "专属天使", "烟火为聘", "那么骄傲", "时间煮雨", "最后一页", "为你写诗", "寂寞烟火", "云烟成雨", "夏天的风", "我好想你", "如果可以", "可不可以", "多喜欢你", "不是故意", "修炼爱情", "会飞的贼", "荒唐的羊", "爱丫爱丫", "有何不可", "无人之岛", "半句再见", "晴天和猫", "几分之几", "小步舞曲", "山高路远", "六月的雨", "好久不见", "牛仔很忙", "豆浆油条"]
WU = ["背对背拥抱", "客官不可以", "私奔到月球", "如果没有你", "当爱在靠近", "最长的电影", "东京不太热", "我超喜欢你", "可惜没如果", "旅行的意义", "匿名的好友", "还是会寂寞", "慢慢喜欢你", "外面的世界", "我的歌声里", "心愿便利贴", "突然好想你", "握不住的他", "不想做朋友", "出现又离开", "走在冷风中", "勇气大爆发", "奇妙能力歌"]
LIU = ["99次我爱他", "123我爱你", "321对不起", "七秒钟的记忆", "情人节的夜晚", "离开地球表面", "爱的双重魔力", "遥不可及的你", "蒲公英的约定", "有可能的夜晚", "不分手的恋爱", "说好的幸福呢", "我是你的小狗", "阿拉斯加海湾"]
LONG_EN = ["After 17", "Forever 21", "April Encounter"]
LONG_CN = ["当我唱起这首歌", "远在北方孤独的鬼", "一个人想着一个人", "你就不要想起我", "我喜欢上你时的内心活动", "一个像夏天一个像秋天", "那些你很冒险的梦", "考试什么的都去死吧", "二十岁的某一天", "给我一首歌的时间", "这世界那么多人", "遇见你的时候所有星星都落到我头上", "第57次取消发送", "你被写在我的歌里", "我不愿让你一个人", "刻在我心底的名字"]


def build_default_library() -> SongLibrary:
    """构造内置库（全部 active）。

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
            songs.append(Song(title=t, status="active", section=sec))
    return SongLibrary(songs=songs)
