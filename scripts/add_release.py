#!/usr/bin/env python3
"""Add one immutable plugin release to registry/index.json."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from validate_registry import (
    INDEX_PATH,
    ROOT,
    canonical_hash,
    load_json,
    validate_manifest,
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "manifest", type=Path, help="plugins/<id>/<version>/manifest.json"
    )
    parser.add_argument("--trust", choices=("official", "reviewed"), default="reviewed")
    parser.add_argument("--repository-url", required=True)
    parser.add_argument("--documentation-url")
    parser.add_argument("--unlisted", action="store_true")
    return parser.parse_args()


def write_atomic(path: Path, value: dict) -> None:
    rendered = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    descriptor, temporary = tempfile.mkstemp(
        prefix=".index-", suffix=".json", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(rendered)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> int:
    args = arguments()
    manifest_path = args.manifest.resolve()
    try:
        relative_path = manifest_path.relative_to(ROOT).as_posix()
    except ValueError as error:
        raise SystemExit("manifest 必须位于 QHub 仓库内") from error
    manifest = load_json(manifest_path)
    validate_manifest(manifest, relative_path)
    plugin_id = manifest["id"]
    version = manifest["version"]
    expected_path = f"plugins/{plugin_id}/{version}/manifest.json"
    if relative_path != expected_path:
        raise SystemExit(f"manifest 必须保存为 {expected_path}")

    registry = load_json(INDEX_PATH)
    plugins = registry.setdefault("plugins", [])
    plugin = next((item for item in plugins if item.get("id") == plugin_id), None)
    if plugin is None:
        plugin = {
            "id": plugin_id,
            "trust": args.trust,
            "listed": not args.unlisted,
            "repository_url": args.repository_url,
            "releases": [],
        }
        plugins.append(plugin)
    elif plugin.get("trust") != args.trust:
        raise SystemExit("已有插件的 trust 不能通过发布脚本修改")
    if args.documentation_url:
        plugin["documentation_url"] = args.documentation_url
    if any(item.get("version") == version for item in plugin["releases"]):
        raise SystemExit(f"{plugin_id}@{version} 已存在；不可覆盖，请提升版本")
    plugin["releases"].append(
        {
            "version": version,
            "path": relative_path,
            "manifest_hash": canonical_hash(manifest),
            "published_at": datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "manifest": manifest,
        }
    )
    plugins.sort(key=lambda item: item["id"])
    registry["revision"] = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    write_atomic(INDEX_PATH, registry)
    print(f"Added {plugin_id}@{version}; run python3 scripts/validate_registry.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
