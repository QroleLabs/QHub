# 搭建 QScene 兼容插件注册表

QHub 是 QScene 默认的官方源，但 QScene 不绑定单一注册地址。管理员可以在“平台管理 →
市场治理 → 插件源”添加、编辑、启停或移除多个公开注册表。

## 最小结构

兼容源使用与 QHub 相同的目录和 JSON 契约：

```text
registry/index.json
plugins/<plugin-id>/<semver>/manifest.json
schemas/plugin-manifest.schema.json
schemas/registry.schema.json
```

`registry/index.json` 的 `name` 和 `repository` 应改为运营方自己的名称及公开 HTTPS 仓库。
每个 release 同时包含 Manifest 快照、路径、发布时间和规范化 SHA-256。完整字段以
[`registry.schema.json`](../schemas/registry.schema.json) 为准。

## 复用 QHub 工具

可以 fork QHub，修改注册表身份后使用兼容模式验证：

```bash
python3 scripts/add_release.py \
  plugins/dev.example.my-plugin/1.0.0/manifest.json \
  --trust reviewed \
  --repository-url https://github.com/example/my-plugin

python3 scripts/validate_registry.py --compatible
```

若需要检查相对已发布 commit 的不可变历史：

```bash
python3 scripts/validate_registry.py \
  --compatible \
  --base-ref <previous-commit-sha>
```

QHub 自身 CI 不使用 `--compatible`，因此仍会严格要求官方名称和仓库地址。

## 托管要求

- `registry/index.json` 必须通过无凭据、无 query/fragment 的公开 HTTPS 地址提供；
- 不得指向 localhost、私有或保留 IP；
- 服务器应提供 ETag，以减少 QScene 的重复下载；
- 单个索引最大 5 MiB，单个 Manifest 最大 1 MiB；
- 已发布的 `plugin id + version` 不得覆盖或删除，变更必须提升 SemVer；
- 下架插件应设置 `listed: false`，保留历史 release。

## QScene 中的来源隔离

每个注册表源在 QScene 中独立记录 URL、信任等级、revision、ETag、摘要和错误状态。插件 ID
只能归属于一个源，另一个源不能抢占。源级“审核来源”会把其中所有插件的最高信任等级限制
为 reviewed；只有管理员明确设为“官方信任”的源才能展示 official 插件。

停用源只暂停同步并保留当前目录。移除源会下架其插件，但不会删除历史 release、用户安装
或插件数据；重新添加相同地址时可以继续使用原来源记录。
