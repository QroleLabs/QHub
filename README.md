# QHub

QHub 是 [QScene](https://github.com/QroleLabs/QScene) 的官方插件注册表。它保存经过审核的
不可变插件 Manifest；QScene 定时读取
[`registry/index.json`](./registry/index.json)，因此新增和升级插件不再需要修改 QScene
源码或新增数据库种子迁移。

QHub 是注册表，不是第三方代码执行仓库。当前插件均使用 QScene 提供的声明式运行时，
QScene 不会从插件仓库下载或执行 JavaScript、CSS、Python、二进制文件或 hooks。

## 开发者入口

- [插件开发完整说明](./docs/plugin-development.md)
- [贡献与发布流程](./CONTRIBUTING.md)
- [Manifest JSON Schema](./schemas/plugin-manifest.schema.json)
- [注册表 JSON Schema](./schemas/registry.schema.json)
- [安全策略](./SECURITY.md)

## 注册表地址

QScene 默认读取以下只读地址：

```text
https://raw.githubusercontent.com/QroleLabs/QHub/main/registry/index.json
```

注册表中的每个 release 都包含规范化 Manifest 和 SHA-256。相同插件版本一经合并不得
覆盖；任何内容变化必须提升 SemVer。QScene 会再次验证结构、权限、兼容性和哈希，并把
安装固定到具体 release 快照。

## 添加一个版本

将 Manifest 放到固定目录，然后使用辅助脚本生成索引项：

```bash
mkdir -p plugins/dev.example.context-tools/1.0.0
cp /path/to/qscene-plugin.manifest.json \
  plugins/dev.example.context-tools/1.0.0/manifest.json

python3 scripts/add_release.py \
  plugins/dev.example.context-tools/1.0.0/manifest.json \
  --trust reviewed \
  --repository-url https://github.com/example/context-tools \
  --documentation-url https://github.com/example/context-tools#readme

python3 scripts/validate_registry.py
```

第三方插件必须使用 `reviewed`；`official` 只由 QroleLabs 维护者授予。提交 Pull Request
后，QHub CI 会执行同一套零依赖校验。

## 仓库布局

```text
QHub/
├── registry/index.json
├── plugins/<plugin-id>/<semver>/manifest.json
├── schemas/
├── scripts/
└── docs/
```

The registry and contributor documentation are public so third-party authors can build and review
plugins without access to the QScene deployment or source tree.
