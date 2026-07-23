"""去水印：用右侧相邻纯色区域水平镜像补丁遮盖左下角「AI生成」水印。

原样迁移自 歌单-排版一\build_playlist.py 的 remove_watermark()，行为不变。
"""
from PIL import Image, ImageFilter


def remove_watermark(img):
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
