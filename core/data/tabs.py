"""曲谱附件存储层（data/tabs/{song_id}/{文件}）。

R0.5（契约 design/contracts/R0.5-song-relations.md §4.4/§7）：
- 物理目录以不可变 song_id 为键，歌曲改名不移动目录；
- Song.tab_files 继续保存相对 data/ 的路径（如 "tabs/song_ab12…/主歌.png"）；
- 旧 tabs/{title}/ 目录由 migrate_title_dirs 搬迁：可 dry-run、冲突不覆盖、
  成功后旧目录移入可恢复备份、重复运行无副作用。
"""
import hashlib
import os
import re
import shutil
import unicodedata

ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".pdf"}
MAX_FILE_BYTES = 10 * 1024 * 1024  # 10MB，手机拍的谱子照片足够

# Song.id 格式（core/data/songs.py：song_<uuid hex>），目录键严格校验防穿越
SONG_ID_RE = re.compile(r"^song_[0-9a-f]{32}$")

# 迁移备份默认位置（tabs_root 下），调用方可传 backup_root 覆盖
DEFAULT_BACKUP_DIRNAME = ".migration-backup"


def sanitize_name(name: str) -> str:
    """文件名安全清洗：去路径分隔符与开头点，防目录穿越。"""
    name = unicodedata.normalize("NFC", name or "")
    name = name.replace("/", "_").replace("\\", "_").strip().lstrip(".")
    return name[:80] or "未命名"


def _song_dir(tabs_root: str, song_id: str) -> str:
    if not SONG_ID_RE.match(song_id or ""):
        raise ValueError(f"非法 song_id：{song_id!r}（曲谱目录只接受稳定 song_id）")
    return os.path.join(tabs_root, song_id)


def save_tab(tabs_root: str, song_id: str, filename: str, data: bytes) -> str:
    """保存曲谱文件，返回相对 data/ 的路径（如 tabs/song_…/主歌.png）。

    扩展名白名单校验；重名自动加 -1/-2 后缀；超尺寸抛 ValueError。
    """
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED_EXT:
        raise ValueError(f"不支持的文件类型：{ext or '（无扩展名）'}（允许 {sorted(ALLOWED_EXT)}）")
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f"文件超过 {MAX_FILE_BYTES // 1024 // 1024}MB 上限")
    base = sanitize_name(os.path.splitext(os.path.basename(filename))[0])
    d = _song_dir(tabs_root, song_id)
    os.makedirs(d, exist_ok=True)
    candidate, i = f"{base}{ext}", 1
    while os.path.exists(os.path.join(d, candidate)):
        candidate = f"{base}-{i}{ext}"
        i += 1
    with open(os.path.join(d, candidate), "wb") as f:
        f.write(data)
    return f"tabs/{song_id}/{candidate}"


def delete_tab(tabs_root: str, song_id: str, relpath: str) -> bool:
    """删除曲谱文件。relpath 必须落在该歌 ID 目录内（防目录穿越）。返回是否删除成功。"""
    if not SONG_ID_RE.match(song_id or ""):
        raise ValueError(f"非法 song_id：{song_id!r}")
    prefix = f"tabs/{song_id}/"
    if not relpath.startswith(prefix) or ".." in relpath:
        return False
    abs_path = os.path.join(os.path.dirname(tabs_root), relpath)
    if os.path.isfile(abs_path):
        os.unlink(abs_path)
        return True
    return False


def rewrite_tab_files(tab_files: list, title: str, song_id: str) -> list:
    """把 tab_files 中旧 title 目录前缀改写为 ID 目录前缀；其余项原样保留。"""
    old_prefix = f"tabs/{sanitize_name(title)}/"
    new_prefix = f"tabs/{song_id}/"
    return [new_prefix + f[len(old_prefix):] if f.startswith(old_prefix) else f
            for f in tab_files]


# ── 旧 title 目录迁移 ──


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _list_dirs(tabs_root: str) -> list:
    if not os.path.isdir(tabs_root):
        return []
    return sorted(d for d in os.listdir(tabs_root)
                  if os.path.isdir(os.path.join(tabs_root, d)) and d != DEFAULT_BACKUP_DIRNAME)


def plan_migration(tabs_root: str, id_by_dirname: dict) -> dict:
    """纯扫描不写盘。id_by_dirname: {sanitize_name(title): song_id}。

    返回 {planned, unchanged, unresolved, conflicts}：
    - planned：[{dirname, song_id, files}] 待搬迁的 title 目录；
    - unchanged：已是 ID 目录（含曾迁移过的）；
    - unresolved：无法映射到 song_id 的目录名（保留原地，进报告）；
    - conflicts：目标已存在同名但内容不同的文件（不覆盖，整目录停止）。
    """
    planned, unchanged, unresolved, conflicts = [], [], [], []
    for dirname in _list_dirs(tabs_root):
        if SONG_ID_RE.match(dirname):
            unchanged.append(dirname)
            continue
        song_id = id_by_dirname.get(dirname)
        if not song_id:
            unresolved.append(dirname)
            continue
        src_dir = os.path.join(tabs_root, dirname)
        dst_dir = os.path.join(tabs_root, song_id)
        files = sorted(f for f in os.listdir(src_dir)
                       if os.path.isfile(os.path.join(src_dir, f)))
        dir_conflicts = []
        for f in files:
            dst_file = os.path.join(dst_dir, f)
            if os.path.isfile(dst_file) and _sha256(dst_file) != _sha256(os.path.join(src_dir, f)):
                dir_conflicts.append(f)
        if dir_conflicts:
            conflicts.append({"dirname": dirname, "song_id": song_id, "files": dir_conflicts})
        else:
            planned.append({"dirname": dirname, "song_id": song_id, "files": files})
    return {"planned": planned, "unchanged": unchanged,
            "unresolved": unresolved, "conflicts": conflicts}


def migrate_title_dirs(tabs_root: str, id_by_dirname: dict,
                       backup_root: str = None, apply: bool = False) -> dict:
    """执行/预演 title 目录 → song_id 目录搬迁。幂等；失败保留旧目录。

    apply=False：只返回计划（dry-run），不写任何文件。
    apply=True：
      1. 逐文件 os.rename 到 ID 目录（同分区原子）；目标同名同哈希视为已迁移跳过；
      2. 逐文件校验 sha256 与源一致；
      3. 全部成功后把旧目录移入 backup_root（默认 tabs/.migration-backup/），不删除；
      4. 任何一步失败：已搬文件留在 ID 目录（合法状态），旧目录保留，可重跑续搬。
    返回报告：planned/unchanged/unresolved/conflicts/moved/backups/errors。
    """
    report = plan_migration(tabs_root, id_by_dirname)
    report["moved"] = []
    report["backups"] = []
    report["errors"] = []
    if not apply:
        return report
    if report["conflicts"]:
        # 契约 §7.4：任何目录存在冲突时，本次 apply 全局零写入。
        # 不能先迁移无冲突目录再返回失败，否则无法把一次执行视为原子迁移批次。
        return report

    backup_root = backup_root or os.path.join(tabs_root, DEFAULT_BACKUP_DIRNAME)

    for item in report["planned"]:
        dirname, song_id = item["dirname"], item["song_id"]
        src_dir = os.path.join(tabs_root, dirname)
        dst_dir = os.path.join(tabs_root, song_id)
        # 1. 逐文件搬迁（同名同哈希跳过 → 幂等）
        moved_files = []
        try:
            os.makedirs(dst_dir, exist_ok=True)
            for f in item["files"]:
                src_file = os.path.join(src_dir, f)
                dst_file = os.path.join(dst_dir, f)
                if os.path.isfile(dst_file) and _sha256(dst_file) == _sha256(src_file):
                    os.unlink(src_file)  # 内容一致：源视为已迁移，去重
                    continue
                expected = _sha256(src_file)
                os.rename(src_file, dst_file)
                moved_files.append((f, expected))
        except OSError as e:
            report["errors"].append({"dirname": dirname, "error": str(e)})
            continue
        # 2. 校验：数量 + 哈希
        ok = True
        for f, expected in moved_files:
            dst_file = os.path.join(dst_dir, f)
            if not os.path.isfile(dst_file) or _sha256(dst_file) != expected:
                report["errors"].append({"dirname": dirname, "error": f"校验失败：{f}"})
                ok = False
        if not ok:
            continue
        # 3. 旧目录移入可恢复备份（仅剩空目录/隐藏文件时整体搬走）
        try:
            os.makedirs(backup_root, exist_ok=True)
            backup_dst = os.path.join(backup_root, dirname)
            i = 1
            while os.path.exists(backup_dst):
                backup_dst = os.path.join(backup_root, f"{dirname}-{i}")
                i += 1
            shutil.move(src_dir, backup_dst)
            report["backups"].append(backup_dst)
        except OSError as e:
            report["errors"].append({"dirname": dirname, "error": f"旧目录归档失败：{e}"})
        report["moved"].append({"dirname": dirname, "song_id": song_id,
                                "files": [f for f, _ in moved_files]})
    return report
