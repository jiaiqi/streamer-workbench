"""统一测试入口（R0.12）：一个命令跑全部 Python 测试。

- 自动注入 PYTHONUTF8=1 与 PYTHONPATH=项目根，Windows 控制台不再依赖手工设环境变量；
- 使用当前解释器运行，建议在项目 .venv 中调用：`python tools/run_tests.py`；
- 可选参数：只跑指定文件，如 `python tools/run_tests.py test_golden test_unit`。
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEST_DIR = PROJECT_ROOT / "tests"


def main(argv: list[str]) -> int:
    selected = [arg if arg.endswith(".py") else f"{arg}.py" for arg in argv]
    if selected:
        files = [TEST_DIR / name for name in selected]
        missing = [str(f) for f in files if not f.is_file()]
        if missing:
            print(f"测试文件不存在：{', '.join(missing)}")
            return 2
    else:
        files = sorted(TEST_DIR.glob("test_*.py"))

    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(PROJECT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")

    print(f"共 {len(files)} 个测试文件，解释器：{sys.executable}\n")
    failures: list[tuple[str, str]] = []
    started = time.monotonic()
    for path in files:
        name = path.name
        mark = time.monotonic()
        result = subprocess.run(
            [sys.executable, str(path)],
            cwd=PROJECT_ROOT, env=env,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        output = (result.stdout + result.stderr).strip()
        last_lines = "\n".join(output.splitlines()[-3:])
        if result.returncode == 0:
            print(f"✅ {name}（{time.monotonic() - mark:.1f}s）")
            if "diff=0" in output or "passed" not in output:
                for line in output.splitlines()[-2:]:
                    print(f"   {line}")
        else:
            failures.append((name, last_lines))
            print(f"❌ {name}（{time.monotonic() - mark:.1f}s）")
            print(f"   {last_lines}")

    elapsed = time.monotonic() - started
    print(f"\n{'=' * 60}")
    if failures:
        print(f"失败 {len(failures)}/{len(files)}：{', '.join(name for name, _ in failures)}")
        return 1
    print(f"全部通过 {len(files)}/{len(files)}，耗时 {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
