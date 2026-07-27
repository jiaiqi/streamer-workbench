"""曲谱附件存储层（data/tabs/{歌名}/{文件}）。

Song.tab_files 存相对 data/ 的路径（如 "tabs/知足/主歌.png"），
server 层把 data/tabs 挂到 /tabs 静态路由后，前端直接用 "/tabs/知足/主歌.png" 访问。
设计见 design/roadmap-data-stats.md 第 5 节。
"""
import os
import unicodedata

ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".pdf"}
MAX_FILE_BYTES = 10 * 1024 * 1024  # 10MB，手机拍的谱子照片足够


def sanitize_name(name: str) -> str:
    """文件名/歌名目录名安全清洗：去路径分隔符与开头点，防目录穿越。"""
    name = unicodedata.normalize("NFC", name or "")
    name = name.replace("/", "_").replace("\\", "_").strip().lstrip(".")
    return name[:80] or "未命名"


def _song_dir(tabs_root: str, title: str) -> str:
    return os.path.join(tabs_root, sanitize_name(title))


def save_tab(tabs_root: str, title: str, filename: str, data: bytes) -> str:
    """保存曲谱文件，返回相对 data/ 的路径（如 tabs/知足/主歌.png）。

    扩展名白名单校验；重名自动加 -1/-2 后缀；超尺寸抛 ValueError。
    """
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED_EXT:
        raise ValueError(f"不支持的文件类型：{ext or '（无扩展名）'}（允许 {sorted(ALLOWED_EXT)}）")
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f"文件超过 {MAX_FILE_BYTES // 1024 // 1024}MB 上限")
    base = sanitize_name(os.path.splitext(os.path.basename(filename))[0])
    d = _song_dir(tabs_root, title)
    os.makedirs(d, exist_ok=True)
    candidate, i = f"{base}{ext}", 1
    while os.path.exists(os.path.join(d, candidate)):
        candidate = f"{base}-{i}{ext}"
        i += 1
    with open(os.path.join(d, candidate), "wb") as f:
        f.write(data)
    return f"tabs/{sanitize_name(title)}/{candidate}"


def delete_tab(tabs_root: str, title: str, relpath: str) -> bool:
    """删除曲谱文件。relpath 必须落在该歌目录内（防目录穿越）。返回是否删除成功。"""
    prefix = f"tabs/{sanitize_name(title)}/"
    if not relpath.startswith(prefix) or ".." in relpath:
        return False
    abs_path = os.path.join(os.path.dirname(tabs_root), relpath)
    if os.path.isfile(abs_path):
        os.unlink(abs_path)
        return True
    return False
