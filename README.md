# QHub

QHub 是 [QScene](https://github.com/QroleLabs/QScene) 默认的官方插件注册表。QScene 也支持
管理员添加其他兼容注册表源。QHub 保存经过审核的
不可变插件 Manifest；QScene 定时读取
[`registry/index.json`](./registry/index.json)，因此新增和升级插件不再需要修改 QScene
源码或新增数据库种子迁移。

QHub 是注册表，不是代码分发或执行仓库。QScene 支持现有声明式 runtime，以及仅随
QScene 镜像发布、由 QroleLabs 审核的 `internal.python.v1` Handler。QScene 不会从 QHub
或插件仓库下载 Python、JavaScript、CSS、二进制文件或在线安装依赖。

当前第三方投稿入口关闭。注册表继续保留兼容注册表、`reviewed` 信任级别和投稿所需的
数据契约，供以后恢复扩展；目前 QHub 新增 release 仅由 QroleLabs 维护者操作。

## 维护者入口

- [插件开发完整说明](./docs/plugin-development.md)
- [贡献与发布流程](./CONTRIBUTING.md)
- [Manifest JSON Schema](./schemas/plugin-manifest.schema.json)
- [注册表 JSON Schema](./schemas/registry.schema.json)
- [安全策略](./SECURITY.md)
- [搭建兼容注册表](./docs/registry-hosting.md)

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
  plugins/qscene.example-tools/1.0.0/manifest.json \
  --trust official \
  --repository-url https://github.com/QroleLabs/QScene \
  --documentation-url https://github.com/QroleLabs/QScene/tree/main/plugins/official/qscene.example-tools/README.md

python3 scripts/validate_registry.py
```

`official` 只由 QroleLabs 维护者授予。第三方投稿恢复后只能使用 `reviewed`，但当前此
入口不开放。提交 Pull Request 后，QHub CI 会执行同一套零依赖校验。

## 仓库布局

```text
QHub/
├── registry/index.json
├── plugins/<plugin-id>/<semver>/manifest.json
├── schemas/
├── scripts/
└── docs/
```

注册表规范公开，便于审计并为以后恢复第三方生态保留兼容性；当前可执行的内部插件代码
只存在于 QScene 构建上下文中。
