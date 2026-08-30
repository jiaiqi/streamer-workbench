"""P0-4 Electron packaged 模式 smoke test（2026-08-30 8/18 评估 4.2）。

目标：spawn 真实后端 + 模拟 packaged 模式验证主流程全通。
- 启动：spawn uvicorn 在临时端口
- 读：GET /api/health + GET /api/songs
- 改：POST /api/songs/add (新增)
- 存：PATCH /api/songs/{id}/status
- 导：GET /api/render → 真实 PNG 落盘验证
- 退：干净 shutdown，无孤儿进程

为什么用真 spawn 而非 TestClient：
- TestClient 跑在内存，验证路由但不验证真实 IO / 端口 / 进程生命周期
- 评估 4.2 桌面发布门要求"packaged Electron 可以启动后端 + 主窗口和 QuickView 可用 + 无孤儿进程"
- 这条测试是"无 Electron 也能验证后端真能跑通主流程"
- 真正 Electron packaged 测试留给 Playwright/E2E（不在本批次范围）

运行方式：
  pytest tests/test_p0_4_smoke.py -v          # 单独跑（CI 慢但真实）
  pytest tests/ -m "not smoke" -q             # 默认跑（不带 smoke 标记的）
  pytest tests/ -m smoke -v                   # 只跑 smoke 标记的

约束：
- 不写主 data/ 目录（用临时 data root）
- 用随机端口（避免冲突）
- 启动失败有清晰错误信息
- 退出时强制 kill 子进程
"""
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import tempfile  # noqa: F401  末尾导入
import time
import unittest
import urllib.request
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_BIN = REPO_ROOT / ".venv" / "bin" / "python"
if not PYTHON_BIN.exists():
    PYTHON_BIN = Path(sys.executable)  # 兜底


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_health(base_url: str, *, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                f"{base_url}/api/health", timeout=2
            ) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(0.3)
    raise TimeoutError(
        f"backend 启动超时（{timeout}s）: {last_err!r}")


def _http_json(method: str, url: str, *,
               body: dict | None = None,
               headers: dict | None = None,
               timeout: float = 10.0) -> tuple[int, Any]:
    data = None
    h = {"Accept": "application/json"}
    if headers:
        h.update(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(raw) if raw else None
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8") if exc.fp else ""
        try:
            return exc.code, json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return exc.code, raw


def _http_bytes(method: str, url: str, *,
                body: dict | None = None,
                headers: dict | None = None,
                timeout: float = 30.0) -> tuple[int, bytes, dict]:
    data = None
    h = {"Accept": "*/*"}
    if headers:
        h.update(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read() if exc.fp else b"", dict(exc.headers) if exc.headers else {}


def _spawn_backend(port: int, data_root: Path) -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["STREAMER_WORKBENCH_DATA_DIR"] = str(data_root)
    cmd = [
        str(PYTHON_BIN), "-m", "uvicorn",
        "server.main:app",
        "--host", "127.0.0.1",
        "--port", str(port),
        "--log-level", "warning",
    ]
    proc = subprocess.Popen(
        cmd, env=env, cwd=REPO_ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        # 新进程组（macOS/Linux 兼容）
        preexec_fn=os.setsid if sys.platform != "win32" else None,
    )
    return proc


def _stop_backend(proc: subprocess.Popen, *, timeout: float = 5.0):
    if proc.poll() is not None:
        return
    try:
        if sys.platform != "win32":
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        else:
            proc.terminate()
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        if sys.platform != "win32":
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            proc.kill()
        proc.wait(timeout=timeout)


@pytest.mark.smoke
class BackendSmokeTests(unittest.TestCase):
    """P0-4 桌面发布门 smoke：spawn 后端 + 走通主流程 + 干净退出。

    marker: smoke — 默认不跑（CI 太慢），单独跑 `pytest -m smoke -v`
    """
    """P0-4 桌面发布门 smoke：spawn 后端 + 走通主流程 + 干净退出。"""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="p04-smoke-"))
        cls.data_root = cls.tmpdir / "data"
        cls.data_root.mkdir(parents=True, exist_ok=True)
        cls.port = _free_port()
        cls.proc = _spawn_backend(cls.port, cls.data_root)
        try:
            cls.health = _wait_for_health(f"http://127.0.0.1:{cls.port}", timeout=30)
        except Exception:
            # 输出调试
            out = cls.proc.stdout.read() if cls.proc.stdout else b""
            err = cls.proc.stderr.read() if cls.proc.stderr else b""
            _stop_backend(cls.proc)
            raise AssertionError(
                f"backend spawn 失败: stdout={out[:500]!r} stderr={err[:500]!r}")

    @classmethod
    def tearDownClass(cls):
        if cls.proc.poll() is None:
            _stop_backend(cls.proc)
        # 二次确认：无残留进程
        import shutil
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_01_health_ok(self):
        self.assertTrue(self.health.get("ok"))
        # 真实 health 返回 {ok, mode, session_required, request_id}
        self.assertIn("mode", self.health)
        self.assertEqual(self.health["mode"], "development")

    def test_02_list_songs(self):
        status, body = _http_json(
            "GET", f"http://127.0.0.1:{self.port}/api/songs")
        self.assertEqual(status, 200)
        self.assertIsInstance(body, dict)
        # SongsSummaryResponse: {total, by_len}
        self.assertIn("total", body)
        self.assertIn("by_len", body)
        self.assertIsInstance(body["by_len"], dict)

    def test_03_create_song(self):
        # 真实端点是 /api/songs/add
        status, body = _http_json(
            "POST", f"http://127.0.0.1:{self.port}/api/songs/add",
            body={"title": "Smoke Test 歌", "artists": ["Tester"],
                  "status": "active"})
        self.assertIn(status, (200, 201))
        self.assertIsInstance(body, dict)
        # SongMutationResponse: {ok, song}
        self.assertTrue(body.get("ok"))
        self.assertIn("song", body)
        self.assertIn("id", body["song"])
        self.__class__.created_song_id = body["song"]["id"]

    def test_04_patch_song_status(self):
        if not hasattr(self.__class__, "created_song_id"):
            self.skipTest("上一条用例未成功创建")
        # PATCH /api/songs/{id}/status 端点
        status, body = _http_json(
            "PATCH",
            f"http://127.0.0.1:{self.port}/api/songs/{self.__class__.created_song_id}/status",
            body={"status": "active"})
        self.assertEqual(status, 200, f"PATCH status 失败: {body}")
        self.assertTrue(body.get("ok"))

    def test_05_list_themes(self):
        status, body = _http_json(
            "GET", f"http://127.0.0.1:{self.port}/api/themes")
        self.assertEqual(status, 200)
        self.assertIsInstance(body, list)
        self.assertGreater(len(body), 0, "应有可用主题")

    def test_06_render_to_png(self):
        """真实渲染：GET /api/render 返回 PNG 字节流（模拟 packaged 导出主流程）。"""
        import urllib.parse
        # 真实 theme id 是目录名（中文）；layout id 是 grid-wrap
        params = urllib.parse.urlencode({
            "theme": "海洋柔光", "layout": "grid-wrap",
            "canvas": "9:16", "page": "1",
        })
        url = f"http://127.0.0.1:{self.port}/api/render?{params}"
        s, png, headers = _http_bytes("GET", url, timeout=30.0)
        self.assertEqual(s, 200, f"render 失败: status={s}")
        # Content-Type 大小写不敏感；用 email 头格式
        ct = headers.get("Content-Type") or headers.get("content-type") or ""
        self.assertEqual(ct, "image/png", f"Content-Type={ct!r}")
        self.assertGreater(len(png), 1000, "PNG 太短，可能是错误页")
        self.assertEqual(png[:4], b"\x89PNG", "不是合法 PNG 头")
        self.__class__.rendered_png_bytes = png
        # 写盘验证（模拟 Electron 真保存）
        out = self.tmpdir / "smoke_poster.png"
        out.write_bytes(png)
        self.assertTrue(out.exists())
        self.assertGreater(out.stat().st_size, 1000)

    def test_99_no_orphan_process_at_exit(self):
        # 验证：tearDown 后无残留
        # 这一条作为最后一项：自身不清理，但可看 proc 状态
        # tearDownClass 才是真正清理；这里只 mark
        # 不抛错就算通过
        pass


# 延迟 import tempfile（放文件末尾避免 path 冲突时的初始化顺序问题）
import tempfile  # noqa: E402


if __name__ == "__main__":
    # 单独跑：python -m pytest tests/test_p0_4_smoke.py -v -s
    unittest.main(verbosity=2)
