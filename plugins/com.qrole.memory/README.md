# 长期记忆

QScene 官方 `memory.v1` 插件。用户可以按全局、角色或会话范围维护自己的长期记忆，平台
在相关对话中检索并注入有限长度的上下文。

- 稳定 ID：`com.qrole.memory`（为兼容既有安装与数据保留历史名称）
- 权限：`chat:memory`
- 配置：`top_k`、`max_context_chars`
- 数据边界：只能读取当前用户在该插件下保存的记忆

安装会固定到具体 Manifest release。插件不执行第三方代码，也不会读取其他用户的聊天或
记忆。
