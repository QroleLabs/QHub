# QScene 插件开发说明

本文面向希望把插件发布到 QHub 的第三方开发者。QScene 插件 v1 是由平台解释执行的
声明式 Manifest，不是浏览器扩展、Node 包或任意后端代码。

## 1. 先选择 runtime

| runtime | 必需权限 | 用途 | 可读取或改变的内容 |
| --- | --- | --- | --- |
| `prompt.v1` | `chat:context` | 为对话附加经过审核的系统上下文 | 只注入 Manifest 中固定的 prompt 和明确标记为 runtime-visible 的非敏感配置 |
| `memory.v1` | `chat:memory` | 使用用户自己维护的长期记忆 | 只检索当前用户、当前角色或当前会话范围的数据 |
| `model-preference.v1` | `chat:model-preference` | 设置新对话默认渠道模型 | 只能选择管理员启用并配置积分计费的模型 |

QScene 不执行 Manifest 中的 JS、CSS、Python、二进制文件、hooks 或任意网络回调。如果
需求无法由现有 runtime 表达，应先向 QScene 提出新的、可隔离的 runtime 设计；仅在这种
情况下才需要升级 QScene 本身。

## 2. 创建开发仓库

推荐结构：

```text
my-plugin/
├── qscene-plugin.manifest.json
├── README.md
├── LICENSE
└── tests/
```

将编辑器的 JSON Schema 指向：

```text
https://raw.githubusercontent.com/QroleLabs/QHub/main/schemas/plugin-manifest.schema.json
```

## 3. 编写 Manifest

最小 `prompt.v1` 示例：

```json
{
  "$schema": "https://raw.githubusercontent.com/QroleLabs/QHub/main/schemas/plugin-manifest.schema.json",
  "schema_version": "1",
  "id": "dev.example.context-tools",
  "name": "Context Tools",
  "version": "1.0.0",
  "description": "在长对话中跟踪尚未解决的线索。",
  "category": "效率",
  "keywords": ["context", "writing"],
  "author": {"name": "Example Dev", "url": "https://example.com"},
  "repository": "https://github.com/example/context-tools",
  "documentation": "https://github.com/example/context-tools#readme",
  "license": "MIT",
  "runtime": {
    "type": "prompt.v1",
    "prompt": "Track unresolved threads and surface them only when relevant."
  },
  "permissions": ["chat:context"],
  "compatibility": {"platform_api": ">=1.0.0 <2.0.0"},
  "config_schema": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "compact": {
        "type": "boolean",
        "title": "精简输出",
        "default": true,
        "x-runtime-visible": true
      }
    }
  }
}
```

字段约束：

- `id` 是全局稳定标识，建议使用反向域名；发布后不得转移或修改。
- `version` 必须是完整 SemVer，例如 `1.2.0`，不能使用 `latest`。
- `permissions` 必须与 runtime 精确匹配，不接受未实现或多余权限。
- `compatibility.platform_api` 声明可运行的平台 API 范围。
- Manifest 规范化后最大 1 MiB；关键词最多 20 个。
- URL 必须是无内嵌用户名或密码的公开 HTTPS 地址。

## 4. 配置参数

`config_schema` 使用受限的 JSON Schema object。支持 `string`、`number`、`integer`、
`boolean`、默认值、枚举和基本长度或数值范围。

普通配置默认只保存在插件安装记录中。只有属性明确声明
`"x-runtime-visible": true` 时，`prompt.v1` 才能在运行时读取该非敏感标量。

QHub 不接受下列配置：

- API Key、Token、密码、Cookie、JWT、Bearer 或登录凭据；
- 数据库连接串、DSN、会话密钥；
- `writeOnly`、`x-sensitive` 或 `format: password` 字段；
- 试图创建渠道、读取渠道 Base URL/密钥或绕过 QScene 积分计费的字段。

## 5. Runtime 示例

`memory.v1`：

```json
{
  "runtime": {"type": "memory.v1"},
  "permissions": ["chat:memory"],
  "config_schema": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "top_k": {"type": "integer", "minimum": 1, "maximum": 20, "default": 8},
      "max_context_chars": {"type": "integer", "minimum": 500, "maximum": 12000, "default": 4000}
    }
  }
}
```

`model-preference.v1` 必须把 `channel_model_id` 声明为必填字符串。安装界面会渲染安全的
模型选择器，开发者不能提供任意 URL 或密钥输入框：

```json
{
  "runtime": {"type": "model-preference.v1"},
  "permissions": ["chat:model-preference"],
  "config_schema": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "channel_model_id": {"type": "string", "title": "默认渠道模型"}
    },
    "required": ["channel_model_id"]
  }
}
```

完整 Manifest 仍需包含第 3 节列出的所有必填字段。

## 6. 本地验证与发布

Fork 并克隆 QHub，把 Manifest 保存到不可变目录：

```bash
plugins/<plugin-id>/<version>/manifest.json
```

然后运行：

```bash
python3 scripts/add_release.py \
  plugins/dev.example.context-tools/1.0.0/manifest.json \
  --trust reviewed \
  --repository-url https://github.com/example/context-tools \
  --documentation-url https://github.com/example/context-tools#readme

python3 scripts/validate_registry.py
```

辅助脚本会把 Manifest 快照写入单文件注册表、计算 SHA-256 并更新 registry revision。
它会拒绝覆盖已有版本。之后提交 Pull Request，并附上：

- 插件仓库与不可变 tag；
- 功能说明和截图（如适用）；
- 每项权限的必要性；
- Manifest 和 prompt 的测试方式；
- 许可证及第三方内容来源。

第三方提交只能选择 `reviewed`。`official` 表示由 QroleLabs 直接维护，由 QHub 维护者设置。

## 7. 安装、升级和下架语义

QScene 定时同步 QHub，但用户安装会固定到具体 release。QHub 新增 `1.1.0` 后，现有
`1.0.0` 安装不会静默变化；用户明确升级后才切换。如果新版本新增权限，用户必须重新
确认授权。

插件下架不会删除用户数据，但平台会阻止重新安装或启用。注册表不得移除插件条目，
历史 release 也必须保留，以便审计和解释已固定安装的版本；下架只设置
`listed: false`。

## 8. 安全设计建议

- Prompt 中把用户或外部内容当作不可信数据，不要要求其覆盖系统规则。
- 只申请 runtime 唯一允许的权限。
- 不要声称能够访问实际并未提供的聊天、用户、渠道或管理员数据。
- 不要把密钥或个人数据写进 Manifest、Issue、测试快照和日志。
- 每次发布前查看规范化 diff，确认没有无意增加权限或 runtime-visible 配置。

QScene 在同步时仍会独立验证 Manifest、哈希和兼容性；QHub CI 通过不等于运行时校验会被
跳过。
