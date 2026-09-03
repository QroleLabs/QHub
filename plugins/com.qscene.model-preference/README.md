# 自定义渠道模型

QScene 官方 `model-preference.v1` 插件。用户可以从管理员已经启用并配置积分计费的渠道
模型中选择一个，作为新建对话的默认模型。

- 稳定 ID：`com.qscene.model-preference`
- 权限：`chat:model-preference`
- 配置：`channel_model_id`
- 显式选择优先：聊天页手动选择和已有会话模型不会被覆盖
- 安全回退：所选模型停用或取消计费后，新对话使用平台默认模型

插件只保存平台内部模型 ID，不接触渠道 Base URL 或 API Key，也不会绕过 QScene 积分
计费。
