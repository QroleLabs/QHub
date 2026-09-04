from __future__ import annotations

import copy
import unittest

from scripts.validate_registry import RegistryError, validate_manifest


def manifest() -> dict[str, object]:
    return {
        "schema_version": "1",
        "id": "qscene.test-internal",
        "name": "Internal Test",
        "version": "1.0.0",
        "description": "test",
        "runtime": {
            "type": "internal.python.v1",
            "entrypoint": "plugin:create_plugin",
        },
        "capabilities": ["context-provider.v1"],
        "permissions": ["chat:context"],
    }


class InternalRuntimeManifestTests(unittest.TestCase):
    def test_valid_manifest(self) -> None:
        validate_manifest(manifest(), "test")

    def test_capability_requires_exact_permission(self) -> None:
        value = manifest()
        value["permissions"] = ["chat:action"]
        with self.assertRaisesRegex(RegistryError, "Capability"):
            validate_manifest(value, "test")

    def test_capability_must_be_implemented_and_unique(self) -> None:
        unknown = manifest()
        unknown["capabilities"] = ["ui-panel.v1"]
        with self.assertRaisesRegex(RegistryError, "Capability"):
            validate_manifest(unknown, "test")

        duplicate = manifest()
        duplicate["capabilities"] = [
            "context-provider.v1",
            "context-provider.v1",
        ]
        with self.assertRaisesRegex(RegistryError, "Capability"):
            validate_manifest(duplicate, "test")

    def test_entrypoint_must_use_factory(self) -> None:
        value = copy.deepcopy(manifest())
        value["runtime"]["entrypoint"] = "plugin:run"
        with self.assertRaisesRegex(RegistryError, "create_plugin"):
            validate_manifest(value, "test")


if __name__ == "__main__":
    unittest.main()
