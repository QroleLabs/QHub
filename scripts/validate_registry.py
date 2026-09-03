#!/usr/bin/env python3
"""Validate the QHub registry with no third-party Python dependencies."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import sys
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = ROOT / "registry" / "index.json"
MAX_INDEX_BYTES = 5 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
PLUGIN_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,159}$")
SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
PERMISSION = re.compile(r"^[a-z][a-z0-9._-]*:[a-z][a-z0-9._:-]*$")
RUNTIME_PERMISSIONS = {
    "prompt.v1": "chat:context",
    "memory.v1": "chat:memory",
    "model-preference.v1": "chat:model-preference",
}
SENSITIVE_PARTS = {
    "auth",
    "authorization",
    "bearer",
    "cookie",
    "credential",
    "credentials",
    "dsn",
    "jwt",
    "key",
    "passphrase",
    "passwd",
    "password",
    "secret",
    "secrets",
    "session",
    "token",
    "tokens",
}


class RegistryError(ValueError):
    pass


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RegistryError(f"JSON 包含重复字段：{key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_object)
    except (OSError, json.JSONDecodeError) as error:
        raise RegistryError(f"无法读取 {path.relative_to(ROOT)}：{error}") from error
    if not isinstance(value, dict):
        raise RegistryError(f"{path.relative_to(ROOT)} 顶层必须是对象")
    return value


def canonical_hash(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RegistryError(message)


def validate_https_url(value: Any, field: str) -> None:
    require(isinstance(value, str) and len(value) <= 2000, f"{field} 必须是 URL")
    parsed = urlparse(value)
    require(
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None,
        f"{field} 必须是无凭据的 HTTPS URL",
    )
    try:
        address = ipaddress.ip_address(parsed.hostname or "")
    except ValueError:
        return
    require(not (address.is_private or address.is_loopback or address.is_link_local), f"{field} 不能指向私有地址")


def _is_sensitive(name: str, definition: Any) -> bool:
    definition = definition if isinstance(definition, dict) else {}
    if definition.get("writeOnly") is True or definition.get("x-sensitive") is True:
        return True
    if str(definition.get("format") or "").lower() == "password":
        return True
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    parts = {part for part in re.split(r"[^A-Za-z0-9]+", separated.lower()) if part}
    if parts == {"public", "key"}:
        return False
    return bool(parts & SENSITIVE_PARTS) or {"connection", "string"}.issubset(parts)


def validate_manifest(manifest: dict[str, Any], context: str) -> None:
    required = {"schema_version", "id", "name", "version", "description", "runtime", "permissions"}
    missing = sorted(required - manifest.keys())
    require(not missing, f"{context} 缺少字段：{', '.join(missing)}")
    require(manifest.get("schema_version") == "1", f"{context}.schema_version 只支持 1")
    plugin_id = manifest.get("id")
    require(isinstance(plugin_id, str) and bool(PLUGIN_ID.fullmatch(plugin_id)), f"{context}.id 非法")
    version = manifest.get("version")
    require(isinstance(version, str) and bool(SEMVER.fullmatch(version)), f"{context}.version 必须是完整 SemVer")
    require(isinstance(manifest.get("name"), str) and 0 < len(manifest["name"].strip()) <= 160, f"{context}.name 非法")
    require(isinstance(manifest.get("description"), str) and len(manifest["description"]) <= 4000, f"{context}.description 非法")
    encoded = json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    require(len(encoded) <= MAX_MANIFEST_BYTES, f"{context} 超过 1 MiB")

    runtime = manifest.get("runtime")
    require(isinstance(runtime, dict), f"{context}.runtime 必须是对象")
    runtime_type = runtime.get("type")
    if runtime_type == "prompt":
        runtime_type = "prompt.v1"
    require(runtime_type in RUNTIME_PERMISSIONS, f"{context} 使用了 QHub 尚未支持的 runtime")
    permissions = manifest.get("permissions")
    require(isinstance(permissions, list) and len(permissions) <= 32, f"{context}.permissions 非法")
    require(len(permissions) == len(set(permissions)), f"{context}.permissions 不能重复")
    require(all(isinstance(item, str) and PERMISSION.fullmatch(item) for item in permissions), f"{context}.permissions 格式非法")
    required_permission = RUNTIME_PERMISSIONS[runtime_type]
    require(permissions == [required_permission], f"{context} 的权限必须且只能是 {required_permission}")
    if runtime_type == "prompt.v1":
        require(isinstance(runtime.get("prompt"), str) and bool(runtime["prompt"].strip()), f"{context}.runtime.prompt 不能为空")
    if runtime_type == "model-preference.v1":
        schema = manifest.get("config_schema")
        properties = schema.get("properties") if isinstance(schema, dict) else None
        channel_model = properties.get("channel_model_id") if isinstance(properties, dict) else None
        required_fields = schema.get("required") if isinstance(schema, dict) else None
        require(
            isinstance(channel_model, dict)
            and channel_model.get("type") == "string"
            and isinstance(required_fields, list)
            and "channel_model_id" in required_fields,
            f"{context} 必须声明必填字符串 channel_model_id",
        )

    schema = manifest.get("config_schema")
    properties = schema.get("properties") if isinstance(schema, dict) else {}
    require(isinstance(properties, dict), f"{context}.config_schema.properties 必须是对象")
    sensitive = sorted(name for name, definition in properties.items() if _is_sensitive(name, definition))
    require(not sensitive, f"{context} 不允许敏感配置字段：{', '.join(sensitive)}")
    for field in ("repository", "homepage", "documentation"):
        if manifest.get(field) is not None:
            validate_https_url(manifest[field], f"{context}.{field}")


def validate_registry() -> tuple[int, int]:
    require(INDEX_PATH.stat().st_size <= MAX_INDEX_BYTES, "registry/index.json 超过 5 MiB")
    registry = load_json(INDEX_PATH)
    require(registry.get("schema_version") == "1", "registry.schema_version 只支持 1")
    require(registry.get("name") == "QHub", "registry.name 必须是 QHub")
    require(isinstance(registry.get("revision"), str) and bool(registry["revision"].strip()), "registry.revision 不能为空")
    validate_https_url(registry.get("repository"), "registry.repository")
    plugins = registry.get("plugins")
    require(isinstance(plugins, list) and len(plugins) <= 10000, "registry.plugins 必须是数组")

    plugin_ids: set[str] = set()
    indexed_paths: set[str] = set()
    release_count = 0
    for plugin_index, plugin in enumerate(plugins):
        context = f"plugins[{plugin_index}]"
        require(isinstance(plugin, dict), f"{context} 必须是对象")
        plugin_id = plugin.get("id")
        require(isinstance(plugin_id, str) and bool(PLUGIN_ID.fullmatch(plugin_id)), f"{context}.id 非法")
        require(plugin_id not in plugin_ids, f"重复插件 id：{plugin_id}")
        plugin_ids.add(plugin_id)
        require(plugin.get("trust") in {"official", "reviewed"}, f"{context}.trust 非法")
        require(isinstance(plugin.get("listed"), bool), f"{context}.listed 必须是布尔值")
        validate_https_url(plugin.get("repository_url"), f"{context}.repository_url")
        if plugin.get("documentation_url") is not None:
            validate_https_url(plugin["documentation_url"], f"{context}.documentation_url")
        releases = plugin.get("releases")
        require(isinstance(releases, list) and releases, f"{context}.releases 不能为空")
        versions: set[str] = set()
        for release_index, release in enumerate(releases):
            release_context = f"{context}.releases[{release_index}]"
            require(isinstance(release, dict), f"{release_context} 必须是对象")
            version = release.get("version")
            require(isinstance(version, str) and bool(SEMVER.fullmatch(version)), f"{release_context}.version 非法")
            require(version not in versions, f"{plugin_id} 存在重复版本 {version}")
            versions.add(version)
            expected_path = f"plugins/{plugin_id}/{version}/manifest.json"
            path = release.get("path")
            require(path == expected_path and PurePosixPath(path).as_posix() == path, f"{release_context}.path 必须是 {expected_path}")
            require(path not in indexed_paths, f"重复 manifest 路径：{path}")
            indexed_paths.add(path)
            manifest_path = ROOT / path
            require(manifest_path.is_file(), f"缺少 {path}")
            manifest_file = load_json(manifest_path)
            manifest_inline = release.get("manifest")
            require(isinstance(manifest_inline, dict), f"{release_context}.manifest 必须是对象")
            require(manifest_file == manifest_inline, f"{release_context}.manifest 与 {path} 不一致")
            validate_manifest(manifest_inline, f"{plugin_id}@{version}")
            require(manifest_inline.get("id") == plugin_id, f"{release_context} 的 manifest.id 不匹配")
            require(manifest_inline.get("version") == version, f"{release_context} 的 manifest.version 不匹配")
            digest = release.get("manifest_hash")
            require(isinstance(digest, str) and bool(SHA256.fullmatch(digest)), f"{release_context}.manifest_hash 非法")
            require(digest == canonical_hash(manifest_inline), f"{release_context}.manifest_hash 校验失败")
            published_at = release.get("published_at")
            require(isinstance(published_at, str), f"{release_context}.published_at 必须是时间")
            try:
                datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            except ValueError as error:
                raise RegistryError(f"{release_context}.published_at 非法") from error
            release_count += 1

    disk_paths = {
        path.relative_to(ROOT).as_posix()
        for path in ROOT.glob("plugins/*/*/manifest.json")
    }
    require(indexed_paths == disk_paths, f"索引与插件目录不一致；未索引={sorted(disk_paths - indexed_paths)}，缺失={sorted(indexed_paths - disk_paths)}")
    return len(plugin_ids), release_count


def main() -> int:
    try:
        plugin_count, release_count = validate_registry()
    except (RegistryError, OSError) as error:
        print(f"QHub validation failed: {error}", file=sys.stderr)
        return 1
    print(f"Validated {plugin_count} plugin(s), {release_count} immutable release(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
