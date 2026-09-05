#!/usr/bin/env python3
"""Validate the QHub registry with no third-party Python dependencies."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from functools import total_ordering
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = ROOT / "registry" / "index.json"
QHUB_REPOSITORY_URL = "https://github.com/QroleLabs/QHub"
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
    "relationship.v1": "chat:relationship",
    "model-preference.v1": "chat:model-preference",
}
INTERNAL_RUNTIME = "internal.python.v1"
INTERNAL_CAPABILITY_PERMISSIONS = {
    "context-provider.v1": "chat:context",
    "chat-action.v1": "chat:action",
    "role-card-inspector.v1": "role-card:inspect",
    "event-handler.v1": "events:observe",
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


@total_ordering
@dataclass(frozen=True)
class SemVer:
    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] | None = None

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        core = (self.major, self.minor, self.patch)
        other_core = (other.major, other.minor, other.patch)
        if core != other_core:
            return core < other_core
        if self.prerelease is None:
            return False
        if other.prerelease is None:
            return True
        for left, right in zip(self.prerelease, other.prerelease):
            if left == right:
                continue
            left_numeric = left.isdigit()
            right_numeric = right.isdigit()
            if left_numeric and right_numeric:
                return int(left) < int(right)
            if left_numeric != right_numeric:
                return left_numeric
            return left < right
        return len(self.prerelease) < len(other.prerelease)


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


def load_json_text(value: str, context: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value, object_pairs_hook=_object)
    except json.JSONDecodeError as error:
        raise RegistryError(f"{context} 不是有效 JSON：{error}") from error
    if not isinstance(parsed, dict):
        raise RegistryError(f"{context} 顶层必须是对象")
    return parsed


def parse_semver(value: str) -> SemVer:
    require(bool(SEMVER.fullmatch(value)), f"无效 SemVer：{value}")
    without_build = value.split("+", 1)[0]
    core, separator, prerelease_value = without_build.partition("-")
    major, minor, patch = (int(part) for part in core.split("."))
    prerelease = tuple(prerelease_value.split(".")) if separator else None
    return SemVer(major, minor, patch, prerelease)


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
        hostname = (parsed.hostname or "").lower()
        require(
            hostname != "localhost" and not hostname.endswith(".local"),
            f"{field} 不能指向本地主机",
        )
        return
    require(
        not (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
            or address.is_unspecified
        ),
        f"{field} 不能指向私有或保留地址",
    )


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
    required = {
        "schema_version",
        "id",
        "name",
        "version",
        "description",
        "runtime",
        "permissions",
    }
    missing = sorted(required - manifest.keys())
    require(not missing, f"{context} 缺少字段：{', '.join(missing)}")
    require(manifest.get("schema_version") == "1", f"{context}.schema_version 只支持 1")
    plugin_id = manifest.get("id")
    require(
        isinstance(plugin_id, str) and bool(PLUGIN_ID.fullmatch(plugin_id)),
        f"{context}.id 非法",
    )
    version = manifest.get("version")
    require(
        isinstance(version, str) and bool(SEMVER.fullmatch(version)),
        f"{context}.version 必须是完整 SemVer",
    )
    require(
        isinstance(manifest.get("name"), str)
        and 0 < len(manifest["name"].strip()) <= 160,
        f"{context}.name 非法",
    )
    require(
        isinstance(manifest.get("description"), str)
        and len(manifest["description"]) <= 4000,
        f"{context}.description 非法",
    )
    encoded = json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    require(len(encoded) <= MAX_MANIFEST_BYTES, f"{context} 超过 1 MiB")

    runtime = manifest.get("runtime")
    require(isinstance(runtime, dict), f"{context}.runtime 必须是对象")
    runtime_type = runtime.get("type")
    if runtime_type == "prompt":
        runtime_type = "prompt.v1"
    require(
        runtime_type in {*RUNTIME_PERMISSIONS, INTERNAL_RUNTIME},
        f"{context} 使用了 QHub 尚未支持的 runtime",
    )
    permissions = manifest.get("permissions")
    require(
        isinstance(permissions, list) and len(permissions) <= 32,
        f"{context}.permissions 非法",
    )
    require(
        len(permissions) == len(set(permissions)), f"{context}.permissions 不能重复"
    )
    require(
        all(
            isinstance(item, str) and PERMISSION.fullmatch(item) for item in permissions
        ),
        f"{context}.permissions 格式非法",
    )
    if runtime_type == INTERNAL_RUNTIME:
        capabilities = manifest.get("capabilities")
        require(
            isinstance(capabilities, list)
            and bool(capabilities)
            and len(capabilities) == len(set(capabilities))
            and all(
                capability in INTERNAL_CAPABILITY_PERMISSIONS
                for capability in capabilities
            ),
            f"{context}.capabilities 必须是非空且仅包含已实现 Capability 的数组",
        )
        expected_permissions = {
            INTERNAL_CAPABILITY_PERMISSIONS[capability]
            for capability in capabilities
        }
        require(
            set(permissions) == expected_permissions
            and len(permissions) == len(expected_permissions),
            f"{context} 的权限必须与 Capability 精确匹配",
        )
        entrypoint = runtime.get("entrypoint")
        require(
            isinstance(entrypoint, str)
            and 3 <= len(entrypoint) <= 240
            and entrypoint.endswith(":create_plugin"),
            f"{context}.runtime.entrypoint 必须指向 create_plugin",
        )
    else:
        required_permission = RUNTIME_PERMISSIONS[runtime_type]
        require(
            permissions == [required_permission],
            f"{context} 的权限必须且只能是 {required_permission}",
        )
    if runtime_type == "prompt.v1":
        require(
            isinstance(runtime.get("prompt"), str) and bool(runtime["prompt"].strip()),
            f"{context}.runtime.prompt 不能为空",
        )
    if runtime_type == "model-preference.v1":
        schema = manifest.get("config_schema")
        properties = schema.get("properties") if isinstance(schema, dict) else None
        channel_model = (
            properties.get("channel_model_id") if isinstance(properties, dict) else None
        )
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
    require(
        isinstance(properties, dict), f"{context}.config_schema.properties 必须是对象"
    )
    sensitive = sorted(
        name
        for name, definition in properties.items()
        if _is_sensitive(name, definition)
    )
    if runtime_type != INTERNAL_RUNTIME:
        require(not sensitive, f"{context} 不允许敏感配置字段：{', '.join(sensitive)}")
    for field in ("repository", "homepage", "documentation"):
        if manifest.get(field) is not None:
            validate_https_url(manifest[field], f"{context}.{field}")
    author = manifest.get("author")
    if isinstance(author, dict) and author.get("url") is not None:
        validate_https_url(author["url"], f"{context}.author.url")


def validate_registry(*, require_qhub_identity: bool = True) -> tuple[int, int]:
    require(
        INDEX_PATH.stat().st_size <= MAX_INDEX_BYTES, "registry/index.json 超过 5 MiB"
    )
    registry = load_json(INDEX_PATH)
    require(registry.get("schema_version") == "1", "registry.schema_version 只支持 1")
    require(
        isinstance(registry.get("name"), str)
        and 0 < len(registry["name"].strip()) <= 160,
        "registry.name 必须是 1 到 160 个字符",
    )
    require(
        isinstance(registry.get("revision"), str)
        and bool(registry["revision"].strip()),
        "registry.revision 不能为空",
    )
    validate_https_url(registry.get("repository"), "registry.repository")
    if require_qhub_identity:
        require(registry.get("name") == "QHub", "QHub registry.name 必须是 QHub")
        require(
            registry.get("repository") == QHUB_REPOSITORY_URL,
            f"QHub registry.repository 必须是 {QHUB_REPOSITORY_URL}",
        )
    plugins = registry.get("plugins")
    require(
        isinstance(plugins, list) and len(plugins) <= 10000,
        "registry.plugins 必须是数组",
    )

    plugin_ids: set[str] = set()
    indexed_paths: set[str] = set()
    release_count = 0
    for plugin_index, plugin in enumerate(plugins):
        context = f"plugins[{plugin_index}]"
        require(isinstance(plugin, dict), f"{context} 必须是对象")
        plugin_id = plugin.get("id")
        require(
            isinstance(plugin_id, str) and bool(PLUGIN_ID.fullmatch(plugin_id)),
            f"{context}.id 非法",
        )
        require(plugin_id not in plugin_ids, f"重复插件 id：{plugin_id}")
        plugin_ids.add(plugin_id)
        require(
            plugin.get("trust") in {"official", "reviewed"}, f"{context}.trust 非法"
        )
        require(
            isinstance(plugin.get("listed"), bool), f"{context}.listed 必须是布尔值"
        )
        validate_https_url(plugin.get("repository_url"), f"{context}.repository_url")
        if plugin.get("documentation_url") is not None:
            validate_https_url(
                plugin["documentation_url"], f"{context}.documentation_url"
            )
        releases = plugin.get("releases")
        require(isinstance(releases, list) and releases, f"{context}.releases 不能为空")
        versions: set[str] = set()
        parsed_versions: list[SemVer] = []
        for release_index, release in enumerate(releases):
            release_context = f"{context}.releases[{release_index}]"
            require(isinstance(release, dict), f"{release_context} 必须是对象")
            version = release.get("version")
            require(
                isinstance(version, str) and bool(SEMVER.fullmatch(version)),
                f"{release_context}.version 非法",
            )
            require(version not in versions, f"{plugin_id} 存在重复版本 {version}")
            versions.add(version)
            parsed_versions.append(parse_semver(version))
            expected_path = f"plugins/{plugin_id}/{version}/manifest.json"
            path = release.get("path")
            require(
                path == expected_path and PurePosixPath(path).as_posix() == path,
                f"{release_context}.path 必须是 {expected_path}",
            )
            require(path not in indexed_paths, f"重复 manifest 路径：{path}")
            indexed_paths.add(path)
            manifest_path = ROOT / path
            require(manifest_path.is_file(), f"缺少 {path}")
            manifest_file = load_json(manifest_path)
            manifest_inline = release.get("manifest")
            require(
                isinstance(manifest_inline, dict),
                f"{release_context}.manifest 必须是对象",
            )
            require(
                manifest_file == manifest_inline,
                f"{release_context}.manifest 与 {path} 不一致",
            )
            validate_manifest(manifest_inline, f"{plugin_id}@{version}")
            if (
                isinstance(manifest_inline.get("runtime"), dict)
                and manifest_inline["runtime"].get("type") == INTERNAL_RUNTIME
            ):
                require(
                    plugin.get("trust") == "official",
                    f"{plugin_id} 的 internal.python.v1 release 必须为 official",
                )
            require(
                manifest_inline.get("id") == plugin_id,
                f"{release_context} 的 manifest.id 不匹配",
            )
            require(
                manifest_inline.get("version") == version,
                f"{release_context} 的 manifest.version 不匹配",
            )
            digest = release.get("manifest_hash")
            require(
                isinstance(digest, str) and bool(SHA256.fullmatch(digest)),
                f"{release_context}.manifest_hash 非法",
            )
            require(
                digest == canonical_hash(manifest_inline),
                f"{release_context}.manifest_hash 校验失败",
            )
            published_at = release.get("published_at")
            require(
                isinstance(published_at, str),
                f"{release_context}.published_at 必须是时间",
            )
            try:
                parsed_time = datetime.fromisoformat(
                    published_at.replace("Z", "+00:00")
                )
            except ValueError as error:
                raise RegistryError(f"{release_context}.published_at 非法") from error
            require(
                parsed_time.tzinfo is not None,
                f"{release_context}.published_at 必须包含时区",
            )
            release_count += 1
        require(
            parsed_versions == sorted(parsed_versions),
            f"{plugin_id} 的 releases 必须按 SemVer 从低到高排列",
        )

    disk_paths = {
        path.relative_to(ROOT).as_posix()
        for path in ROOT.glob("plugins/*/*/manifest.json")
    }
    require(
        indexed_paths == disk_paths,
        f"索引与插件目录不一致；未索引={sorted(disk_paths - indexed_paths)}，缺失={sorted(indexed_paths - disk_paths)}",
    )
    return len(plugin_ids), release_count


def validate_immutable_history(base_ref: str) -> None:
    require(
        bool(re.fullmatch(r"[0-9a-fA-F]{7,40}", base_ref)),
        "--base-ref 必须是 Git commit SHA",
    )
    completed = subprocess.run(
        ["git", "show", f"{base_ref}:registry/index.json"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RegistryError(f"无法读取基准提交 {base_ref} 的注册表")
    previous = load_json_text(completed.stdout, f"{base_ref}:registry/index.json")
    current = load_json(INDEX_PATH)
    previous_plugins = {
        plugin["id"]: plugin
        for plugin in previous.get("plugins", [])
        if isinstance(plugin, dict) and isinstance(plugin.get("id"), str)
    }
    current_plugins = {
        plugin["id"]: plugin
        for plugin in current.get("plugins", [])
        if isinstance(plugin, dict) and isinstance(plugin.get("id"), str)
    }
    for plugin_id, old_plugin in previous_plugins.items():
        require(
            plugin_id in current_plugins,
            f"已发布插件 {plugin_id} 不得删除；请设置 listed=false",
        )
        new_plugin = current_plugins[plugin_id]
        old_releases = {
            release["version"]: release
            for release in old_plugin.get("releases", [])
            if isinstance(release, dict) and isinstance(release.get("version"), str)
        }
        new_releases = {
            release["version"]: release
            for release in new_plugin.get("releases", [])
            if isinstance(release, dict) and isinstance(release.get("version"), str)
        }
        for version, old_release in old_releases.items():
            require(
                new_releases.get(version) == old_release,
                f"不可变版本被删除或覆盖：{plugin_id}@{version}",
            )
        if old_releases:
            highest_old = max(parse_semver(version) for version in old_releases)
            for version in new_releases.keys() - old_releases.keys():
                require(
                    parse_semver(version) > highest_old,
                    f"{plugin_id} 的新版本 {version} 必须高于已有最高版本",
                )
    if previous != current:
        require(
            previous.get("revision") != current.get("revision"),
            "registry 内容变化时必须更新 revision",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-ref",
        help="验证相对历史 commit 的 release 不可变性",
    )
    parser.add_argument(
        "--compatible",
        action="store_true",
        help="校验第三方兼容注册表，不要求 QHub 名称与仓库地址",
    )
    args = parser.parse_args()
    try:
        plugin_count, release_count = validate_registry(
            require_qhub_identity=not args.compatible
        )
        if args.base_ref:
            validate_immutable_history(args.base_ref)
    except (RegistryError, OSError) as error:
        print(f"QHub validation failed: {error}", file=sys.stderr)
        return 1
    print(f"Validated {plugin_count} plugin(s), {release_count} immutable release(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
