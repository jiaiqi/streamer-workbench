# -*- coding: utf-8 -*-
"""多主题共用歌单海报生成脚本（统一边距全行分布排版 + 同列减栏绕排避让）

用法：python build_playlist.py --theme 主题名 [--fullscreen] [--avoid-rail] [--font 字体] [--tag 标记]
- 主题目录 = 脚本所在目录(ROOT)/<主题名>，背景从该目录读，海报输出到该目录。
- 主题文件夹内只放：背景图、生成的海报、设计理念.md。
- 脚本、字体、歌单数据、提示词文档等公共文件放 ROOT。
所有分类共享统一左右边距：每行整行铺满、最左列严格对齐。"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))  # ROOT
# 默认字体：脚本同目录（ROOT）的猫啃糖圆体；--font 可覆盖
F_REG = os.path.join(BASE, "MaokenAssortedSans.ttf")
F_BOLD = F_REG

W, H = 1080, 1920

# ---------------- 歌单数据 ----------------
YI = ["枫", "耿"]
ER = ["江南","当你","心墙","知足","倔强","温柔","红豆","如愿","传奇","成都","十年","晴天","花海","安静","稻香","搁浅","彩虹","退后","晚婚","再见","偏爱","青柠","怎样","画心","雨爱","鸽子","年轮","抽离","夜车","情话","成全","白羊","泪桥","童话","落霜","遇见"]
SAN = ["坏女孩","他的猫","小恋曲","太聪明","狮子座","最天使","老中医","告诉他","恋爱ing","程艾影","爱一点","他的爱","有点甜","我想念","小星星","吵架歌","黑眼圈","天黑黑","第一天","凑热闹","盗将行","明明就","龙卷风","七里香","园游会","甜甜的","简单爱","千年泪","樱花草","下一秒","小幸运","那些年","下雨天","甜不辣","好想你","哈哈哈","我知道","恶作剧","小情歌","晚安喵","勇敢爱","大舌头","吉他手"]
SI = ["后会无期","忽然之间","匆匆那年","阴天快乐","我们的爱","依然爱你","一笑倾城","专属味道","万有引力","我怀念的","开始懂了","等你下课","专属天使","烟火为聘","那么骄傲","时间煮雨","最后一页","为你写诗","寂寞烟火","云烟成雨","夏天的风","我好想你","如果可以","可不可以","多喜欢你","不是故意","修炼爱情","会飞的贼","荒唐的羊","爱丫爱丫","有何不可","无人之岛","半句再见","晴天和猫","几分之几","小步舞曲","山高路远","六月的雨","好久不见","牛仔很忙","豆浆油条"]
WU = ["背对背拥抱","客官不可以","私奔到月球","如果没有你","当爱在靠近","最长的电影","东京不太热","我超喜欢你","可惜没如果","旅行的意义","匿名的好友","还是会寂寞","慢慢喜欢你","外面的世界","我的歌声里","心愿便利贴","突然好想你","握不住的他","不想做朋友","出现又离开","走在冷风中","勇气大爆发"]
LIU = ["99次我爱他","123我爱你","321对不起","七秒钟的记忆","情人节的夜晚","离开地球表面","爱的双重魔力","遥不可及的你","蒲公英的约定","有可能的夜晚","不分手的恋爱","说好的幸福呢","我是你的小狗","阿拉斯加海湾"]
LONG_EN = ["After 17", "Forever 21", "April Encounter"]
LONG_CN = ["当我唱起这首歌","远在北方孤独的鬼","一个人想着一个人","你就不要想起我","我喜欢上你时的内心活动","一个像夏天一个像秋天","那些你很冒险的梦","考试什么的都去死吧","二十岁的某一天","给我一首歌的时间","这世界那么多人","遇见你的时候所有星星都落到我头上","第57次取消发送","你被写在我的歌里","我不愿让你一个人","刻在我心底的名字"]

# ---------------- 主题预设 ----------------
# 每个主题：prefix 输出文件名前缀；bgs 两页背景文件名（位于 ROOT/<主题名>/ 下）；
# watermark 背景是否需要去水印（AI 生成图左下角「AI生成」水印）；
# style 两页配色（键 1/2 分别对应第 1/2 页）。
_OCEAN = dict(text=(43, 84, 78), label=(36, 110, 96), pill=(188, 224, 210, 130),
              line=(232, 146, 118), mist=(255, 255, 255, 66))
_GRAPE = dict(text=(46, 82, 69), label=(30, 104, 76), pill=(198, 233, 210, 128),
              line=(232, 146, 118), mist=(255, 255, 255, 66))
THEMES = {
    "海洋柔光": dict(
        prefix="梓涵吃不饱-AI海洋歌单-柔光UI版",
        bgs=("background-1.png", "background-2.png"), watermark=False,
        style={1: _OCEAN, 2: _OCEAN}),
    "梦幻海洋": dict(
        prefix="梓涵吃不饱-AI歌单-梦幻海洋版",
        bgs=("bg1.png", "bg2.png"), watermark=True,
        style={1: _OCEAN, 2: _OCEAN}),
    "奶油花园": dict(
        prefix="梓涵吃不饱-AI歌单-奶油花园版",
        bgs=("bg1.png", "bg2.png"), watermark=True,
        style={1: dict(text=(107, 74, 63), label=(138, 74, 56), pill=(247, 199, 178, 118),
                       line=(232, 146, 118), mist=(255, 252, 248, 68)),
               2: dict(text=(95, 70, 88), label=(124, 74, 99), pill=(240, 208, 224, 118),
                       line=(201, 138, 169), mist=(255, 250, 253, 68))}),
    "青提气泡": dict(
        prefix="梓涵吃不饱-AI歌单-青提气泡版",
        bgs=("bg1.png", "bg2.png"), watermark=True,
        style={1: _GRAPE, 2: _GRAPE}),
    # 注：卡通音符旧脚本第 2 页水印位置不同（纵向补丁）；共用脚本统一用标准左下角
    # 水印修复，如第 2 页水印遮盖不干净，需先人工修复背景再跑。
    "卡通音符": dict(
        prefix="梓涵吃不饱-AI歌单-卡通音符版",
        bgs=("bg1.png", "bg2.png"), watermark=True,
        style={1: dict(text=(46, 82, 69), label=(30, 104, 76), pill=(198, 233, 210, 128),
                       line=(232, 146, 118), mist=(255, 255, 255, 60)),
               2: dict(text=(107, 74, 63), label=(138, 74, 56), pill=(247, 199, 178, 128),
                       line=(232, 146, 118), mist=(255, 252, 248, 60))}),
    # 奶油玻璃：专属配色（按背景调色——极浅奶油磨砂玻璃，冷调雾蓝装饰 (208,224,236)）
    # text 深灰蓝保证对比度；label 雾蓝更饱和；pill 冰蓝半透；line 淡珊瑚为唯一暖色点缀；
    # mist alpha 提到 72，压住全屏版落在文字区的玻璃装饰带
    "奶油玻璃": dict(
        prefix="梓涵吃不饱-AI歌单-奶油玻璃版",
        bgs=("background-1.png", "background-2.png"), watermark=False,
        style={1: dict(text=(70, 80, 100), label=(64, 106, 148), pill=(228, 238, 246, 120),
                       line=(230, 158, 148), mist=(255, 255, 255, 72)),
               2: dict(text=(70, 80, 100), label=(64, 106, 148), pill=(228, 238, 246, 120),
                       line=(230, 158, 148), mist=(255, 255, 255, 72))}),
    # 轻复古唱片：专属配色（按背景调色——奶油白底，砖红/铁锈红装饰 (209,151,121)、
    # 深棕唱片 (136,97,82)，装饰全在内容区之下）
    # text 深可可棕；label 陶土/铁锈红；pill 奶橙半透；line 陶土红；mist 暖白
    "轻复古唱片": dict(
        prefix="梓涵吃不饱-AI歌单-轻复古唱片版",
        bgs=("background-1.png", "background-2.png"), watermark=False,
        style={1: dict(text=(96, 70, 58), label=(148, 74, 50), pill=(250, 222, 190, 130),
                       line=(196, 96, 66), mist=(255, 252, 246, 66)),
               2: dict(text=(96, 70, 58), label=(148, 74, 50), pill=(250, 222, 190, 130),
                       line=(196, 96, 66), mist=(255, 252, 246, 66))}),
}

# ---------------- 水印去除 ----------------
def remove_watermark(img):
    """用右侧相邻纯色区域水平镜像补丁遮盖左下角 AI生成 水印。
    补丁左/下贴画布边缘保持全覆盖，仅上/右内侧羽化。"""
    img = img.copy()
    W0, H0 = img.size
    x0, y0, x1, y1 = 0, 3600, 420, H0
    pw, ph = x1 - x0, y1 - y0
    src = img.crop((x1, y0, x1 + pw, y1)).transpose(Image.FLIP_LEFT_RIGHT)
    mask = Image.new("L", (pw, ph), 255)
    px = mask.load()
    feather = 70
    for yy in range(feather):
        a = int(255 * yy / feather)
        for xx in range(pw):
            px[xx, yy] = min(px[xx, yy], a)
    for xx in range(feather):
        a = int(255 * xx / feather)
        for yy in range(ph):
            px[pw - 1 - xx, yy] = min(px[pw - 1 - xx, yy], a)
    mask = mask.filter(ImageFilter.GaussianBlur(12))
    img.paste(src, (x0, y0), mask)
    return img

MARGIN = 58
FONT_SONG = 36
FONT_LABEL = 40
ROW_H = 44
LABEL_H = 74
SEC_GAP = 26
# 避让版分界线下方的布局右边界：约等于满宽 6 栏布局第 5 栏的右缘
# （整体右缩约一栏）。硬禁文边界 x>940 不变，留出约 84 px 安全余量。
R_BELOW = 856

def draw_label(d, x, y, text, st, font_label):
    tw = d.textlength(text, font=font_label)
    pad_x, pad_y = 18, 8
    th = font_label.size + 6
    d.rounded_rectangle((x - pad_x, y - pad_y, x + tw + pad_x, y + th + pad_y),
                        radius=18, fill=st["pill"])
    d.text((x, y), text, font=font_label, fill=st["label"])
    uy = y + th + pad_y + 4
    d.rounded_rectangle((x - 2, uy, x + tw + 2, uy + 3), radius=2, fill=st["line"])

def draw_grid(d, songs, cols, y0, x0_area, x1_area, st, font):
    """全行分布：第一列文字从 x0_area 开始，最后一列文字在 x1_area 结束，
    栏间距均分剩余空间。所有分类共享边距、最左列严格对齐。返回栏 x 坐标列表。"""
    colws = []
    for c in range(cols):
        ws = [d.textlength(s, font=font) for i, s in enumerate(songs) if i % cols == c]
        colws.append(max(ws) if ws else 0)
    gutter = max(12, (x1_area - x0_area - sum(colws)) / max(cols - 1, 1))
    positions = []
    cx = x0_area
    for wcol in colws:
        positions.append(cx)
        cx += wcol + gutter
    for i, s in enumerate(songs):
        r, c = divmod(i, cols)
        d.text((positions[c], y0 + r * ROW_H), s, font=font, fill=st["text"])
    return positions

def compose(bg_path, page, out_path, st, clean=False):
    # --fullscreen：9:20 全屏适配画布（1080×2400），背景向上延展，内容整体下移居中
    FULL = "--fullscreen" in sys.argv
    CH = 2400 if FULL else H
    OFF = (CH - H) // 2
    # --avoid-rail：绕排避让抖音右侧头像/点赞/评论/收藏栏。
    # 右边界 R 按行动态取值：行文字顶部 y 满足 y+36<=1080 的行 R=1022（满宽），
    # 其余行 R=R_BELOW=856（整体右缩约一栏，硬禁文边界 x>940 留 84 px 安全余量）；
    # y>1900 区域同样不放文字。字号按备用规则 36→34 全画面统一。
    AVOID = "--avoid-rail" in sys.argv
    song_size = 34 if AVOID else FONT_SONG

    def R_at(y):
        """绕排右边界：返回歌名文字顶部为 y 的行可用的右边界。"""
        if AVOID and y + 36 > 1080:
            return R_BELOW
        return W - MARGIN
    img = Image.open(bg_path).convert("RGB")
    if not clean:
        img = remove_watermark(img)
    if FULL:
        img = img.resize((W, round(img.size[1] * W / img.size[0])), Image.LANCZOS)
        bh = img.size[1]
        canvas = Image.new("RGB", (W, CH), (255, 255, 255))
        strip = img.crop((0, 0, W, 80)).resize((W, CH - bh + 4), Image.BICUBIC)
        strip = strip.filter(ImageFilter.GaussianBlur(6))
        canvas.paste(strip, (0, 0))
        canvas.paste(img, (0, CH - bh))
        img = canvas.convert("RGBA")
    else:
        img = img.resize((W, H), Image.LANCZOS).convert("RGBA")
    font = ImageFont.truetype(F_REG, song_size)
    font_label = ImageFont.truetype(F_BOLD, FONT_LABEL)

    # 柔光层：无边框、向四周消散的半透明遮罩。
    # 避让版四字减为 5 栏、多 2 行（+88px），底边相应下延 88px（1498+OFF），
    # 保证所有文字仍落在柔光上；非避让模式保持 1410+OFF 不变。
    mist_bottom = (1498 if AVOID else 1410) + OFF
    mist = Image.new("RGBA", (W, CH), (0, 0, 0, 0))
    md = ImageDraw.Draw(mist)
    md.rounded_rectangle((-60, -60, W + 60, mist_bottom), radius=80, fill=st["mist"])
    mist = mist.filter(ImageFilter.GaussianBlur(34))
    img = Image.alpha_composite(img, mist)

    d = ImageDraw.Draw(img)

    def draw_grid_wrap(songs, cols, y0, x0_area):
        """绕排版网格（同列减栏）：
        1. 跨线分类先按整版满宽 R=1022、全部歌名、原栏数计算统一列布局
           （栏内容最大宽度 colws、栏间距、每栏 x 坐标 positions），与无避让时一致；
        2. 分界线上方的行按原栏数、用这组 positions 正常绘制；
        3. 分界线下方的行沿用同一组 positions 的前缀，只从右端去掉会越界
           （positions[k-1]+colws[k-1] > R_BELOW=856）的栏，剩余歌名按行优先、每行 k 个重排；
        4. 上下两块列 x 坐标逐列严格相等，下方行只是少了最右栏。
        整块在分界线上/下的分类维持独立两端对齐；非避让模式等价普通网格。
        返回实际占用的行数。"""
        rows = (len(songs) + cols - 1) // cols
        if not AVOID:
            draw_grid(d, songs, cols, y0, x0_area, R_at(y0), st, font)
            return rows
        r_cut = 0
        while r_cut < rows and y0 + r_cut * ROW_H + 36 <= 1080:
            r_cut += 1
        if r_cut == 0 or r_cut == rows:
            # 整块在分界线一侧：独立按各自 R 两端对齐（没有上块需要对齐）
            draw_grid(d, songs, cols, y0, x0_area, R_at(y0), st, font)
            return rows
        # 跨线：统一列布局（满宽 R=1022、全部歌名、原栏数）
        colws = []
        for c in range(cols):
            ws = [d.textlength(s, font=font) for i, s in enumerate(songs) if i % cols == c]
            colws.append(max(ws) if ws else 0)
        gutter = max(12, (R_at(y0) - x0_area - sum(colws)) / max(cols - 1, 1))
        positions = []
        cx = x0_area
        for wcol in colws:
            positions.append(cx)
            cx += wcol + gutter
        # 分界线上方的行：原栏数、统一列位
        for i in range(r_cut * cols):
            r, c = divmod(i, cols)
            d.text((positions[c], y0 + r * ROW_H), songs[i], font=font, fill=st["text"])
        # 分界线下方的行：沿用列位前缀，从右端去掉越界栏
        k = cols
        while k > 1 and positions[k - 1] + colws[k - 1] > R_BELOW:
            k -= 1
        rest = songs[r_cut * cols:]
        yb = y0 + r_cut * ROW_H
        for i, s in enumerate(rest):
            r, c = divmod(i, k)
            d.text((positions[c], yb + r * ROW_H), s, font=font, fill=st["text"])
        rows_bot = (len(rest) + k - 1) // k
        print(f"  wrap: cols={cols}->{k}, r_cut={r_cut}, "
              f"positions={[round(p, 1) for p in positions]}, "
              f"rows={r_cut}+{rows_bot}")
        return r_cut + rows_bot

    if page == 1:
        y = 100 + OFF
        # 一字（左窄栏） + 二字（右五栏，与三字/四字共享右边距）
        x2 = 200
        draw_label(d, MARGIN, y, "一字", st, font_label)
        draw_label(d, x2, y, "二字", st, font_label)
        y += LABEL_H
        for r, s in enumerate(YI):
            d.text((MARGIN + 4, y + r * ROW_H), s, font=font, fill=st["text"])
        # 一字/二字条带整体在分界线之上，二字网格区域 [200, R_at(行)] = [200, 1022]
        draw_grid(d, ER, 5, y, x2, R_at(y), st, font)
        y += 8 * ROW_H + SEC_GAP
        draw_label(d, MARGIN, y, "三字", st, font_label)
        y += LABEL_H
        # 三字网格跨分界线：同列减栏绕排，按实际占用行数推进
        san_rows = draw_grid_wrap(SAN, 6, y, MARGIN)
        y += san_rows * ROW_H + SEC_GAP
        draw_label(d, MARGIN, y, "四字", st, font_label)
        y += LABEL_H
        # 四字整块在分界线之下：避让版 5 栏两端对齐到 [58, R_BELOW=856]
        # （栏间距加大、右缩约一栏）；非避让模式保持 6 栏满宽
        draw_grid_wrap(SI, 5 if AVOID else 6, y, MARGIN)
    else:
        y = 100 + OFF
        draw_label(d, MARGIN, y, "五字", st, font_label)
        y += LABEL_H
        draw_grid_wrap(WU, 4, y, MARGIN)
        y += 6 * ROW_H + SEC_GAP
        draw_label(d, MARGIN, y, "六字", st, font_label)
        y += LABEL_H
        draw_grid_wrap(LIU, 3, y, MARGIN)
        y += 5 * ROW_H + SEC_GAP
        draw_label(d, MARGIN, y, "长歌名/英文", st, font_label)
        y += LABEL_H
        # 英文在前，其余按短到长；左列从 MARGIN 开始，
        # 右列最宽歌名右缘贴 R_at(行)（两列流在分界线之下，R=R_BELOW=856）
        cn_sorted = sorted(LONG_CN, key=len)
        short = LONG_EN + [s for s in cn_sorted if len(s) <= 9]
        extra = [s for s in cn_sorted if len(s) > 9]
        half = (len(short) + 1) // 2
        left, right = short[:half], short[half:]
        lw = max(d.textlength(s, font=font) for s in left)
        rw = max(d.textlength(s, font=font) for s in right)
        rx = R_at(y) - rw
        for r, s in enumerate(left):
            d.text((MARGIN, y + r * ROW_H), s, font=font, fill=st["text"])
        for r, s in enumerate(right):
            d.text((rx, y + r * ROW_H), s, font=font, fill=st["text"])
        y += half * ROW_H + 12
        # 独占行从 x=MARGIN 起，逐行推进（均在分界线之下）
        for s in extra:
            d.text((MARGIN, y), s, font=font, fill=st["text"])
            y += ROW_H + 4

    img.convert("RGB").save(out_path, "PNG")
    print("saved:", out_path, "last y =", y)

# ---------------- 命令行入口 ----------------
# --theme 主题名（默认海洋柔光）；--classic 强制跳过去水印（否则由主题配置驱动）；
# --font 常规体路径 [粗体路径]；--tag 名称  输出文件名加风格标记
THEME = "海洋柔光"
if "--theme" in sys.argv:
    THEME = sys.argv[sys.argv.index("--theme") + 1]
if THEME not in THEMES:
    raise SystemExit(f"未知主题「{THEME}」，可选：{', '.join(THEMES)}")
th = THEMES[THEME]
THEME_DIR = os.path.join(BASE, THEME)

if "--font" in sys.argv:
    i = sys.argv.index("--font")
    F_REG = sys.argv[i + 1]
    F_BOLD = sys.argv[i + 2] if i + 2 < len(sys.argv) and not sys.argv[i + 2].startswith("--") else F_REG

TAG = None
if "--tag" in sys.argv:
    TAG = sys.argv[sys.argv.index("--tag") + 1]

# 背景标注无水印的主题自动跳过去水印；--classic 可强制跳过
CLEAN = ("--classic" in sys.argv) or (not th["watermark"])

def out_name(page):
    mid = f"-{TAG}" if TAG else ""
    return os.path.join(THEME_DIR, f"{th['prefix']}{mid}-{page}.png")

print(f"theme: {THEME}（背景 {th['bgs'][0]}/{th['bgs'][1]}，{'跳过去水印' if CLEAN else '去水印'}）")
compose(os.path.join(THEME_DIR, th["bgs"][0]), 1, out_name(1), th["style"][1], clean=CLEAN)
compose(os.path.join(THEME_DIR, th["bgs"][1]), 2, out_name(2), th["style"][2], clean=CLEAN)

# 校对
total = len(YI)+len(ER)+len(SAN)+len(SI)+len(WU)+len(LIU)+len(LONG_EN)+len(LONG_CN)
print("total songs:", total)
