"""从 OpenAPI components.schemas 生成无运行时依赖的 TypeScript 类型。"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from tools.export_openapi import export_openapi

DEFAULT_OUTPUT = PROJECT_ROOT / "ui" / "src" / "api" / "generated.ts"


def _type(schema: dict[str, Any]) -> str:
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    if "const" in schema:
        return json.dumps(schema["const"], ensure_ascii=False)
    if "enum" in schema:
        return " | ".join(json.dumps(value, ensure_ascii=False) for value in schema["enum"])
    if "anyOf" in schema:
        return " | ".join(_type(item) for item in schema["anyOf"])
    kind = schema.get("type")
    if isinstance(kind, list):
        return " | ".join(_type({**schema, "type": item}) for item in kind)
    if kind == "array":
        item_type = _type(schema.get("items", {}))
        return f"Array<{item_type}>"
    if kind == "object" or "properties" in schema:
        additional = schema.get("additionalProperties")
        if isinstance(additional, dict):
            return f"Record<string, {_type(additional)}>"
        return "Record<string, unknown>"
    if kind in ("integer", "number"):
        return "number"
    if kind == "boolean":
        return "boolean"
    if kind == "string":
        return "string"
    if kind == "null":
        return "null"
    return "unknown"


def generate(schema: dict[str, Any]) -> str:
    lines = [
        "// 此文件由 tools/generate_api_types.py 生成，请勿手工修改。",
        "// OpenAPI JSON 是临时中间产物；本文件随源码提交。",
        "",
    ]
    schemas = schema.get("components", {}).get("schemas", {})
    for name in sorted(schemas):
        definition = schemas[name]
        properties = definition.get("properties")
        if definition.get("type") == "object" and isinstance(properties, dict):
            required = set(definition.get("required", []))
            lines.append(f"export interface {name} {{")
            for prop_name in sorted(properties):
                optional = "" if prop_name in required else "?"
                lines.append(f"  {json.dumps(prop_name)}{optional}: {_type(properties[prop_name])};")
            if definition.get("additionalProperties") is not False:
                lines.append("  [key: string]: unknown;")
            lines.append("}")
        else:
            lines.append(f"export type {name} = {_type(definition)};")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="生成主播工作台 API TypeScript 类型")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="仅检查已提交产物是否最新")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="streamer-workbench-api-types-") as raw:
        openapi_path = Path(raw) / "openapi.json"
        export_openapi(openapi_path)
        content = generate(json.loads(openapi_path.read_text(encoding="utf-8")))
    if args.check:
        current = args.output.read_text(encoding="utf-8") if args.output.is_file() else ""
        if current != content:
            raise SystemExit(f"API 类型产物不是最新：请运行 {Path(__file__).name}")
        print(f"API 类型产物已同步：{args.output}")
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(f"已生成 API 类型：{args.output}")


if __name__ == "__main__":
    main()
