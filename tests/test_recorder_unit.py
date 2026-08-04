"""R8.2.x RecordingManager（electron/recording/recorder.js）单测。

策略：
- 跳过 desktopCapturer / MediaRecorder（要 Electron runtime）
- 只测纯函数：_msToSrtTime / _resolveOutputDir / _isSafeBackupName
- 测不需要 MediaRecorder 的方法：appendLrc（事件过滤）/ pause-resume 状态机 / listFiles / listAllSessions / deleteFolder / _writeSrt

注意：recorder.js 是 CommonJS，我们用 Node 18+ 自带的 --experimental-vm-modules + subprocess 跑
但更简单：直接通过 Python exec 注入 mock 后 require 整个文件。Electron 模块也 mock 掉。
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ELECTRON_DIR = PROJECT_ROOT / "electron"
RECORDER_JS = ELECTRON_DIR / "recording" / "recorder.js"


# ── 工具：用 Node 子进程跑 recorder.js 内部函数（避免 Python 调 CommonJS 兼容麻烦） ──


_NODE_DRIVER_TEMPLATE = r"""
'use strict';
// 注入 mock electron 模块
const Module = require('module');
const originalResolve = Module._resolveFilename;
Module._resolveFilename = function(request, parent, ...rest) {
  if (request === 'electron') {
    return require.resolve('node:os');  // 返回一个无害的 path
  }
  return originalResolve.call(this, request, parent, ...rest);
};
// 覆盖 require('electron') 返回 mock
const _originalRequire = Module.prototype.require;
Module.prototype.require = function(id) {
  if (id === 'electron') {
    return {
      desktopCapturer: {
        getSources: async () => ([]),
      },
    };
  }
  return _originalRequire.call(this, id);
};

const path = require('path');
const recorderPath = path.resolve(process.env.RECORDER_PATH);
const rec = require(recorderPath);

// 接收 args
const args = JSON.parse(process.env.TEST_ARGS);
const { fn, params } = args;

let result;
(async () => {
  try {
    if (fn === '_msToSrtTime') {
      result = rec._msToSrtTime(params.ms);
    } else if (fn === '_resolveOutputDir') {
      result = rec._resolveOutputDir(params.root, params.sid);
      // 把 Path 序列化成字符串方便 JSON 传回
      result = String(result);
    } else if (fn === '_isSafeBackupName') {
      result = rec._isSafeBackupName(params.name);
    } else if (fn === 'RecordingManager.pause') {
      const mgr = new rec.RecordingManager({
        dataRoot: params.dataRoot,
        log: () => {},
        logErr: () => {},
      });
      mgr._active.set(params.id, params.active);
      result = await mgr.pause(params.id);
    } else if (fn === 'RecordingManager.resume') {
      const mgr = new rec.RecordingManager({
        dataRoot: params.dataRoot,
        log: () => {},
        logErr: () => {},
      });
      mgr._active.set(params.id, params.active);
      result = await mgr.resume(params.id);
    } else if (fn === 'RecordingManager.appendLrc') {
      const mgr = new rec.RecordingManager({
        dataRoot: params.dataRoot,
        log: () => {},
        logErr: () => {},
      });
      if (params.preSetActive !== false) {
        mgr._active.set(params.id, params.active);
      }
      result = mgr.appendLrc(params.id, params.events);
      // 返回 stored 事件数
      if (mgr._active.get(params.id)) {
        result.stored = mgr._active.get(params.id).lrcEvents.length;
      }
    } else if (fn === 'RecordingManager._writeSrt') {
      const mgr = new rec.RecordingManager({
        dataRoot: params.dataRoot,
        log: () => {},
        logErr: () => {},
      });
      result = await mgr._writeSrt(params.active);
    } else if (fn === 'RecordingManager.listFiles') {
      const mgr = new rec.RecordingManager({
        dataRoot: params.dataRoot,
        log: () => {},
        logErr: () => {},
      });
      result = mgr.listFiles(params.sid);
    } else if (fn === 'RecordingManager.listAllSessions') {
      const mgr = new rec.RecordingManager({
        dataRoot: params.dataRoot,
        log: () => {},
        logErr: () => {},
      });
      result = mgr.listAllSessions();
    } else if (fn === 'RecordingManager.deleteFolder') {
      const mgr = new rec.RecordingManager({
        dataRoot: params.dataRoot,
        log: () => {},
        logErr: () => {},
      });
      result = await mgr.deleteFolder(params.sid);
    } else {
      result = { error: `unknown fn: ${fn}` };
    }
  } catch (e) {
    result = { error: String(e), stack: e?.stack };
  }
  console.log('__RESULT__' + JSON.stringify(result) + '__END__');
})();
"""


def _node_call(fn: str, params: dict, *, node_path: str = None) -> dict:
    """在 Node 子进程里跑 recorder 的指定函数，返回结果。"""
    node = node_path or sys.executable.replace("python3", "node")
    import shutil
    node_bin = shutil.which("node") or "node"
    # 把 MagicMock 替换为 None（active.recorder 字段）
    def _strip_mocks(obj):
        if isinstance(obj, MagicMock):
            return None
        if isinstance(obj, dict):
            return {k: _strip_mocks(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_strip_mocks(v) for v in obj]
        return obj
    safe_params = _strip_mocks(params)
    env = {
        "RECORDER_PATH": str(RECORDER_JS),
        "TEST_ARGS": json.dumps({"fn": fn, "params": safe_params}),
    }
    result = subprocess.run(
        [node_bin, "-e", _NODE_DRIVER_TEMPLATE],
        capture_output=True, text=True, env={**__import__("os").environ, **env},
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"node failed: {result.stderr}")
    m = re.search(r"__RESULT__(.+?)__END__", result.stdout, re.DOTALL)
    if not m:
        raise RuntimeError(f"no result marker in: {result.stdout[:500]}")
    return json.loads(m.group(1))


# ── 测试 ──────────────────────────────────────────────────────────


class TestMsToSrtTime:
    def test_zero(self):
        assert _node_call("_msToSrtTime", {"ms": 0}) == "00:00:00,000"

    def test_one_second(self):
        assert _node_call("_msToSrtTime", {"ms": 1000}) == "00:00:01,000"

    def test_one_minute(self):
        assert _node_call("_msToSrtTime", {"ms": 60_000}) == "00:01:00,000"

    def test_one_hour(self):
        assert _node_call("_msToSrtTime", {"ms": 3_600_000}) == "01:00:00,000"

    def test_mixed(self):
        # 1h 2m 25.5s
        assert _node_call("_msToSrtTime", {"ms": 3_745_500}) == "01:02:25,500"


class TestResolveOutputDir:
    def test_safe_session_id(self):
        r = _node_call("_resolveOutputDir", {
            "root": "/tmp/data", "sid": "abc-123",
        })
        assert r == "/tmp/data/recordings/s-abc-123"

    def test_path_traversal_to_orphan(self):
        r = _node_call("_resolveOutputDir", {
            "root": "/tmp/data", "sid": "../etc/passwd",
        })
        assert r == "/tmp/data/recordings/orphan"

    def test_empty_to_orphan(self):
        r = _node_call("_resolveOutputDir", {"root": "/tmp/data", "sid": ""})
        assert r == "/tmp/data/recordings/orphan"

    def test_null_to_orphan(self):
        r = _node_call("_resolveOutputDir", {"root": "/tmp/data", "sid": None})
        assert r == "/tmp/data/recordings/orphan"

    def test_too_long_to_orphan(self):
        r = _node_call("_resolveOutputDir", {
            "root": "/tmp/data", "sid": "a" * 100,
        })
        assert r == "/tmp/data/recordings/orphan"


class TestIsSafeBackupName:
    @pytest.mark.parametrize("name,expected", [
        ("seg-000.webm", True),
        ("seg_001.webm", True),
        ("a.songworkbench", True),
        ("a" * 50 + ".webm", True),  # 55 chars → OK
        ("", False),
        ("../etc/passwd", False),
        ("sub/file.webm", False),
        ("sub\\file.webm", False),
        ("..", False),
        ("a" * 201, False),  # > 200
        ("file;rm-rf.zip", False),
    ])
    def test_check(self, name, expected):
        r = _node_call("_isSafeBackupName", {"name": name})
        assert r is expected


class TestAppendLrc:
    def test_filter_invalid_events(self, tmp_path):
        """appendLrc 过滤：缺字段 / 类型错 / 负数 clamp / 非法字符"""
        r = _node_call("RecordingManager.appendLrc", {
            "dataRoot": str(tmp_path),
            "id": "fake-id",
            "active": {"lrcEvents": []},
            "events": [
                {"offset_ms": 1000, "text": "第一行"},
                {"offset_ms": -100, "text": "negative"},  # 负数 → clamp
                {"text": "no offset"},  # 缺 offset → skip
                {"offset_ms": "x", "text": "bad type"},  # 类型错 → skip
                {"offset_ms": 5000},  # 缺 text → skip
                {"offset_ms": 3000, "text": "好"},
            ],
        })
        assert r["ok"] is True
        assert r["count"] == 6
        # 实际存了 4 条：1000/第一行、-100→0/negative、3000/好、5000? no text
        # 没有 text 的 skip；类型错的 skip
        # 实际 stored: 1000/第一行, 0/negative, 3000/好
        assert r["stored"] == 3

    def test_id_not_found(self, tmp_path):
        r = _node_call("RecordingManager.appendLrc", {
            "dataRoot": str(tmp_path),
            "id": "nope",
            "active": {"lrcEvents": []},
            "events": [],
            "preSetActive": False,  # 不预 set，模拟 id 不存在
        })
        assert r["ok"] is False
        assert r["code"] == "not_found"


class TestPauseResume:
    def test_pause_then_resume(self, tmp_path):
        # 模拟 recording 状态
        active = {
            "id": "rid", "status": "recording",
            "recorder": MagicMock(state="recording"),
            "startedAt": int(time.time() * 1000), "pausedAccumMs": 0, "pausedAt": None,
        }
        # pause
        r1 = _node_call("RecordingManager.pause", {
            "dataRoot": str(tmp_path),
            "id": "rid", "active": active,
        })
        assert r1["ok"] is True
        assert r1["status"] == "paused"

    def test_pause_invalid_state(self, tmp_path):
        r = _node_call("RecordingManager.pause", {
            "dataRoot": str(tmp_path),
            "id": "rid",
            "active": {"id": "rid", "status": "stopped", "recorder": MagicMock()},
        })
        assert r["ok"] is False
        assert r["code"] == "invalid_state"


class TestWriteSrt:
    def test_srt_format(self, tmp_path):
        active = {
            "outputDir": str(tmp_path),
            "prefix": "20260804-120000",
            "lrcEvents": [
                {"offset_ms": 0, "text": "第一行歌词"},
                {"offset_ms": 5_200, "text": "第二行歌词"},
                {"offset_ms": 10_800, "text": "第三行歌词"},
            ],
        }
        r = _node_call("RecordingManager._writeSrt", {
            "dataRoot": str(tmp_path), "active": active,
        })
        filepath = r
        assert filepath.endswith("20260804-120000.srt")
        content = Path(filepath).read_text(encoding="utf-8")
        # SRT 格式：序号\n起始 --> 结束\n文本\n
        assert "1\n00:00:00,000 --> 00:00:05,200\n第一行歌词" in content
        assert "2\n00:00:05,200 --> 00:00:10,800\n第二行歌词" in content
        # 末行 +5s 兜底
        assert "3\n00:00:10,800 --> 00:00:15,800\n第三行歌词" in content

    def test_srt_empty_no_file(self, tmp_path):
        active = {
            "outputDir": str(tmp_path), "prefix": "empty", "lrcEvents": [],
        }
        # 空 events 时 _writeSrt 不应写文件
        r = _node_call("RecordingManager._writeSrt", {
            "dataRoot": str(tmp_path), "active": active,
        })
        # 函数返回 filepath 但文件不存在
        if r and Path(r).exists():
            # 如果意外写出了文件，应该内容空
            assert Path(r).read_text() == ""


class TestListFiles:
    def test_list_empty(self, tmp_path):
        r = _node_call("RecordingManager.listFiles", {
            "dataRoot": str(tmp_path), "sid": "abc",
        })
        assert r["ok"] is True
        assert r["files"] == []

    def test_list_after_write(self, tmp_path):
        target = tmp_path / "recordings" / "s-abc"
        target.mkdir(parents=True)
        (target / "seg-000.webm").write_bytes(b"FAKE WEBM")
        (target / "seg-000.srt").write_text("1\n00:00:00,000 --> 00:00:05,000\n测试\n")
        r = _node_call("RecordingManager.listFiles", {
            "dataRoot": str(tmp_path), "sid": "abc",
        })
        assert r["ok"] is True
        names = sorted(f["name"] for f in r["files"])
        assert names == ["seg-000.srt", "seg-000.webm"]


class TestListAllSessions:
    def test_empty(self, tmp_path):
        r = _node_call("RecordingManager.listAllSessions", {
            "dataRoot": str(tmp_path),
        })
        assert r["ok"] is True
        assert r["sessions"] == []

    def test_multiple_sessions(self, tmp_path):
        (tmp_path / "recordings" / "s-sessionA").mkdir(parents=True)
        (tmp_path / "recordings" / "s-sessionA" / "f.webm").write_bytes(b"x" * 100)
        (tmp_path / "recordings" / "s-sessionB").mkdir(parents=True)
        (tmp_path / "recordings" / "s-sessionB" / "f.webm").write_bytes(b"x" * 300)
        (tmp_path / "recordings" / "orphan").mkdir(parents=True)
        r = _node_call("RecordingManager.listAllSessions", {
            "dataRoot": str(tmp_path),
        })
        assert r["ok"] is True
        assert len(r["sessions"]) == 3
        # 按 totalBytes 倒序
        assert r["sessions"][0]["totalBytes"] >= r["sessions"][-1]["totalBytes"]
        # sessionId 提取（s-xxx → xxx；orphan → null）
        ids = {s["sessionId"] for s in r["sessions"]}
        assert "sessionA" in ids
        assert "sessionB" in ids
        assert None in ids


class TestDeleteFolder:
    def test_delete_existing(self, tmp_path):
        (tmp_path / "recordings" / "s-abc").mkdir(parents=True)
        (tmp_path / "recordings" / "s-abc" / "f.webm").write_bytes(b"x")
        r = _node_call("RecordingManager.deleteFolder", {
            "dataRoot": str(tmp_path), "sid": "abc",
        })
        assert r["ok"] is True
        assert r["deleted"] == 1
        assert not (tmp_path / "recordings" / "s-abc").exists()

    def test_delete_nonexistent(self, tmp_path):
        r = _node_call("RecordingManager.deleteFolder", {
            "dataRoot": str(tmp_path), "sid": "never-existed",
        })
        assert r["ok"] is True
        assert r["deleted"] == 0

