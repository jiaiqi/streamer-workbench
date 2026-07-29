"""导出稳定排序的 OpenAPI JSON；构造应用时不触碰用户数据。"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from server.app import create_app
from server.config import AppConfig


def export_openapi(output: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="streamer-workbench-openapi-") as raw:
        app = create_app(AppConfig(PROJECT_ROOT, mode="test", data_root=Path(raw)))
        schema = app.openapi()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="导出主播工作台 OpenAPI Schema")
    parser.add_argument("output", type=Path, help="OpenAPI JSON 输出路径")
    args = parser.parse_args()
    export_openapi(args.output)


if __name__ == "__main__":
    main()
