"""数据迁移工具（streamer-workbench 根目录下运行）。

子命令：
    bootstrap-songs   历史一次性迁移：内置列表 × 歌单数据.md 交叉校验，生成 songs.json
    r05-relations     R0.5 关系迁移：tabs/{title}→tabs/{song_id}、Preset custom_ids→song_id、
                      songs.json v4→v5 持久化、可选 QuickView 队列快照迁移

R0.5 迁移器契约（design/contracts/R0.5-song-relations.md §7）：
    - 默认 dry-run，不改变任何文件；--apply 才写入
    - 写入前备份 songs/presets/tabs/queue 到 data/backups/r05-migration-<时间戳>/
    - 文件搬迁逐文件校验 sha256；JSON 原子替换；旧目录移入备份不删除
    - 冲突与未解析关系全部进报告，不静默丢失；重复运行无副作用
"""
import argparse
import json
import os
import shutil
import sys
import unicodedata
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.data.songs import SongLibrary, build_default_library
from core.data import tabs as tabs_store
from core.data import presets as presets_store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ═══════════════════ 子命令 1：历史 songs.json 生成 ═══════════════════


def bootstrap_songs():
    """从旧脚本 (build_playlist.py) 和歌单 md 文件交叉校验，生成 songs.json。"""
    data_dir = os.path.join(ROOT, "data")
    os.makedirs(data_dir, exist_ok=True)

    lib = build_default_library()
    builtin_titles = {s.title for s in lib.songs}
    print(f"源 1（songs.py 内置）：{len(builtin_titles)} 首")

    md_path = os.path.join(ROOT, ".archive", "design-docs", "歌单-排版一", "歌单数据.md")
    md_titles = set()
    if os.path.isfile(md_path):
        with open(md_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("## "):
                    continue
                if not line or line.startswith(">") or line.startswith("#"):
                    continue
                for t in line.split(","):
                    t = t.strip()
                    if t:
                        md_titles.add(t)
        print(f"源 2（歌单数据.md）：{len(md_titles)} 首")
    else:
        print(f"⚠️  源 2 缺失：{md_path}，跳过交叉校验")

    if md_titles:
        only_builtin = builtin_titles - md_titles
        only_md = md_titles - builtin_titles
        if only_builtin:
            print(f"❌ 仅在 songs.py 中的歌：{sorted(only_builtin)}")
        if only_md:
            print(f"❌ 仅在 歌单数据.md 中的歌：{sorted(only_md)}")
        if not only_builtin and not only_md:
            print("✅ 双源交叉校验通过（两边歌名完全一致）")
        else:
            print("⚠️  请手动解决差异后重新运行")

    songs_data = {
        "version": 1,
        "songs": [
            {
                "title": s.title, "artists": s.artists, "lyricist": s.lyricist,
                "composer": s.composer, "key": s.key, "capo": s.capo,
                "difficulty": s.difficulty, "tabs": s.tabs, "status": s.status,
                "tags": s.tags, "pinyin": s.pinyin, "added_at": s.added_at,
                "notes": s.notes, "section": s.section,
            }
            for s in lib.songs
        ],
    }
    out_path = os.path.join(data_dir, "songs.json")
    tmp_path = out_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(songs_data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, out_path)
    print(f"\n✅ songs.json 已生成：{out_path}（{len(lib.songs)} 首）")


# ═══════════════════ 子命令 2：R0.5 关系迁移器 ═══════════════════


def _norm_title(title: str) -> str:
    return unicodedata.normalize("NFC", title or "").strip()


def _read_presets(presets_dir: str) -> list:
    """直接读盘列出全部 Preset（不走 init_presets，dry-run 不产生任何写入）。"""
    manifest_path = os.path.join(presets_dir, "manifest.json")
    if not os.path.isfile(manifest_path):
        return []
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    result = []
    for pid in manifest:
        if not presets_store.is_valid_preset_id(pid):
            raise ValueError(f"manifest 包含非法 preset_id：{pid!r}")
        path = os.path.join(presets_dir, pid, "preset.json")
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                result.append(presets_store._from_dict(json.load(f)))
    return result


def run_r05_migration(data_root: str, apply: bool = False, report_path: str = None,
                      queue_path: str = None, queue_out: str = None) -> dict:
    """R0.5 关系迁移主流程。apply=False 为 dry-run（不写任何文件）。

    返回报告 dict；顶层含契约要求的 planned/unchanged/unresolved/conflicts/backups。
    """
    songs_path = os.path.join(data_root, "songs.json")
    tabs_root = os.path.join(data_root, "tabs")
    presets_dir = os.path.join(data_root, "presets")

    # 1. 读取并校验 songs（内存中迁移到 v5），构造映射
    with open(songs_path, "r", encoding="utf-8") as f:
        raw_version = json.load(f).get("version", 1)
    library = SongLibrary.load_from_json(songs_path)
    id_by_dirname = {tabs_store.sanitize_name(s.title): s.id for s in library.songs}
    id_by_title = {_norm_title(s.title): s.id for s in library.songs}

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = os.path.join(data_root, "backups", f"r05-migration-{ts}")
    i = 1
    while os.path.exists(backup_dir):
        backup_dir = os.path.join(data_root, "backups", f"r05-migration-{ts}-{i}")
        i += 1

    report = {"dry_run": not apply, "data_root": data_root,
              "planned": [], "unchanged": [], "unresolved": [],
              "conflicts": [], "backups": []}

    # 2. tabs 目录迁移（核心层自带逐文件 sha256 校验与旧目录归档）
    tabs_report = tabs_store.migrate_title_dirs(
        tabs_root, id_by_dirname,
        backup_root=os.path.join(backup_dir, "tabs") if apply else None,
        apply=apply)
    report["tabs"] = tabs_report
    report["planned"] = [f"tabs/{p['dirname']} → tabs/{p['song_id']}"
                         for p in tabs_report["planned"]]
    report["unchanged"] = [f"tabs/{d}/（已是 ID 目录）" for d in tabs_report["unchanged"]]
    report["unresolved"] = [f"tabs/{d}/（无法匹配歌曲）" for d in tabs_report["unresolved"]]
    report["conflicts"] = [f"tabs/{c['dirname']}/{f}（目标已存在且内容不同）"
                           for c in tabs_report["conflicts"] for f in c["files"]]
    report["backups"] = list(tabs_report["backups"])
    if tabs_report["conflicts"]:
        # 契约 §7.4：发现目标文件冲突时停止，不写任何 JSON
        report["errors"] = ["存在文件冲突，已停止；解决后重新运行"]
        _write_report(report, report_path)
        return report

    # 3. Song.tab_files 路径改写（title 前缀 → ID 前缀）
    rewritten = 0
    for s in library.songs:
        new_tf = tabs_store.rewrite_tab_files(s.tab_files, s.title, s.id)
        if new_tf != s.tab_files:
            s.tab_files = new_tf
            rewritten += 1
    report["tab_files_rewritten"] = rewritten
    report["songs_version_bumped"] = raw_version < SongLibrary.CURRENT_VERSION

    # 4. Preset custom_ids 迁移（未匹配进 unresolved，不丢）
    preset_details = []
    preset_list = _read_presets(presets_dir)
    for p in preset_list:
        res = presets_store.migrate_custom_ids(p, id_by_title)
        if res["changed"]:
            preset_details.append({"id": p.id, "name": p.name,
                                   "resolved": res["resolved"], "unresolved": res["unresolved"]})
            for t in res["unresolved"]:
                report["unresolved"].append(f"preset/{p.id} custom_ids：「{t}」无法匹配")
    report["presets"] = preset_details
    if not preset_details:
        report["unchanged"].append(f"presets（{len(preset_list)} 个无需迁移）")

    # 5. 可选：QuickView 队列快照迁移（契约 §4.1）
    queue_report = None
    if queue_path:
        with open(queue_path, "r", encoding="utf-8") as f:
            queue_items = json.load(f)
        migrated, queue_unresolved = [], []
        for item in queue_items:
            title = _norm_title(str(item.get("title", "")))
            song_id = id_by_title.get(title)
            if song_id:
                migrated.append({"song_id": song_id, "title_snapshot": title,
                                 "sung": bool(item.get("sung")),
                                 "added_at": item.get("addedAt", item.get("added_at", 0))})
            else:
                queue_unresolved.append(title)
                report["unresolved"].append(f"queue：「{title}」无法匹配")
        queue_report = {"migrated": len(migrated), "unresolved": queue_unresolved,
                        "items": migrated}
        report["queue"] = queue_report

    # 6. dry-run 到此为止；apply 先备份再写入
    has_work = (bool(tabs_report["planned"]) or bool(rewritten)
                or report["songs_version_bumped"] or bool(preset_details)
                or bool(queue_report and queue_report["migrated"]))
    if apply and has_work:
        os.makedirs(backup_dir, exist_ok=True)
        shutil.copy2(songs_path, os.path.join(backup_dir, "songs.json"))
        if os.path.isdir(presets_dir):
            shutil.copytree(presets_dir, os.path.join(backup_dir, "presets"))
        if queue_path:
            shutil.copy2(queue_path, os.path.join(backup_dir, os.path.basename(queue_path)))
        report["backups"].append(backup_dir)

        # songs：tab_files 改写 + v5 持久化（原子写，校验由 SongLibrary 内部完成）
        if rewritten or report["songs_version_bumped"]:
            library.save(songs_path)

        # presets：只保存有变化的
        if preset_details:
            changed_ids = {d["id"] for d in preset_details}
            for p in preset_list:
                if p.id in changed_ids:
                    presets_store.save(p, presets_dir)

        # queue：写出迁移后快照
        if queue_report and queue_out:
            tmp = queue_out + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(queue_report["items"], f, ensure_ascii=False, indent=2)
            os.replace(tmp, queue_out)

        # 7. 复验：再扫一遍，planned 应为空（幂等确认）
        verify = tabs_store.plan_migration(tabs_root, id_by_dirname)
        report["verify"] = {
            "remaining_planned": len(verify["planned"]),
            "remaining_conflicts": len(verify["conflicts"]),
        }
    elif apply:
        # 无任何待迁移关系：不写文件、不建备份，真正零副作用
        report["verify"] = {"remaining_planned": 0, "remaining_conflicts": 0,
                            "note": "无待迁移关系，跳过写入"}

    _write_report(report, report_path)
    return report


def _write_report(report: dict, report_path: str = None):
    if report_path:
        os.makedirs(os.path.dirname(os.path.abspath(report_path)), exist_ok=True)
        tmp = report_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        os.replace(tmp, report_path)


# ═══════════════════ CLI ═══════════════════


def main():
    parser = argparse.ArgumentParser(description="数据迁移工具")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("bootstrap-songs", help="历史一次性迁移：交叉校验并生成 songs.json")

    p = sub.add_parser("r05-relations", help="R0.5 关系迁移（默认 dry-run）")
    p.add_argument("--data-root", default=os.path.join(ROOT, "data"), help="数据目录（默认 ./data）")
    p.add_argument("--apply", action="store_true", help="执行迁移（默认只预演）")
    p.add_argument("--report", default=None, help="输出 JSON 报告路径")
    p.add_argument("--queue", default=None, help="可选：QuickView 队列快照 JSON（localStorage 导出）")
    p.add_argument("--queue-out", default=None, help="队列迁移结果输出路径（--apply 时必填）")

    args = parser.parse_args()

    if args.command == "bootstrap-songs":
        bootstrap_songs()
        return

    if args.apply and args.queue and not args.queue_out:
        parser.error("--apply 迁移队列时必须提供 --queue-out")

    report = run_r05_migration(args.data_root, apply=args.apply,
                               report_path=args.report,
                               queue_path=args.queue, queue_out=args.queue_out)

    mode = "DRY-RUN（未写入任何文件）" if report["dry_run"] else "已执行"
    print(f"\n═══ R0.5 关系迁移 · {mode} ═══")
    print(f"planned    ({len(report['planned'])})")
    for x in report["planned"]:
        print(f"  · {x}")
    print(f"unchanged  ({len(report['unchanged'])})")
    print(f"unresolved ({len(report['unresolved'])})")
    for x in report["unresolved"]:
        print(f"  ⚠ {x}")
    print(f"conflicts  ({len(report['conflicts'])})")
    for x in report["conflicts"]:
        print(f"  ✗ {x}")
    print(f"tab_files 改写 {report['tab_files_rewritten']} 首 · "
          f"songs v5 持久化 {'是' if report['songs_version_bumped'] else '否'} · "
          f"preset 迁移 {len(report['presets'])} 个")
    if report.get("queue"):
        print(f"queue 迁移 {report['queue']['migrated']} 条，未解析 {len(report['queue']['unresolved'])} 条")
    if report["backups"]:
        print(f"backups：")
        for b in report["backups"]:
            print(f"  · {b}")
    if report.get("verify"):
        print(f"复验：剩余 planned={report['verify']['remaining_planned']}，"
              f"conflicts={report['verify']['remaining_conflicts']}")
    if args.report:
        print(f"报告已写入：{args.report}")


if __name__ == "__main__":
    main()
