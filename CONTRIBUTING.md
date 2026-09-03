# 向 QHub 发布插件

感谢为 QScene 开发插件。请先阅读
[插件开发说明](./docs/plugin-development.md)，并遵守以下流程。

## Pull Request 清单

1. 在你自己的公开 Git 仓库中维护插件文档和源 Manifest。
2. 为发布版本创建不可变 Git tag；`manifest.version` 使用完整 SemVer。
3. 将完全相同的 Manifest 放到
   `plugins/<manifest.id>/<manifest.version>/manifest.json`。
4. 运行 `scripts/add_release.py`，第三方插件使用 `--trust reviewed`。
5. 运行 `python3 scripts/validate_registry.py`。QHub CI 还会与目标分支的 Git commit 比较，
   拒绝同时改写旧 Manifest 与哈希的提交。
6. 提交 Pull Request，并在说明中附上仓库、tag、功能、权限和测试证据。

## 不可变版本

- 已合并的 `<plugin-id>@<version>` 和 `manifest_hash` 不得修改。
- 修复文案、权限、提示词或配置也必须发布更高版本。
- 不得删除仍可能被用户固定安装的历史 release。
- 需要停止新安装时，请联系维护者将整个插件设为 `listed: false`；历史快照仍保留审计。

## 审核重点

- Manifest ID 是否稳定且属于提交者；
- runtime 和权限是否遵循最小权限原则；
- 提示词是否会诱导泄露系统上下文、凭据或其他用户数据；
- 配置是否包含 API Key、Token、密码、Cookie、连接串等敏感字段；
- 仓库、文档、许可证及版本 tag 是否清晰；
- 更新是否增加权限，以及是否需要用户重新确认授权。

合并表示该 Manifest 快照进入 QHub 市场审核链，不代表 QroleLabs 为第三方内容背书。
维护者可以拒绝、下架或要求修复不安全、误导、侵权或不可维护的插件。
