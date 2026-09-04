# 安全策略

请不要在公开 Issue 中提交未修复的安全漏洞、访问令牌、渠道密钥、用户数据或生产日志。
使用 GitHub 仓库的 **Security → Report a vulnerability** 私密报告入口联系维护者。

QHub 的安全边界：

- 注册表只包含声明式 JSON，不托管、下载或执行 Python/JavaScript/二进制代码；
- `internal.python.v1` 只描述已编入 QScene 镜像、由 QroleLabs 审核的可信纯 Python
  Handler，QHub Manifest 本身不能使代码进入主进程；
- 第三方投稿和上传当前关闭，保留的数据结构不代表授予代码执行权限；
- 插件不得要求 API Key、Token、密码、Cookie、连接串等敏感设置；
- release 通过规范化 JSON 的 SHA-256 固定，相同版本不可覆盖；
- QScene 在同步和每次运行时都会重新验证版本、Manifest 哈希、兼容性及用户授权；
- 插件只能使用 QScene 明确定义的 runtime、Capability 和最小权限；
- GitHub 仓库地址和文档地址只是来源信息，不会被 QScene API 进程克隆或执行。

如果漏洞影响正在运行的 QScene 平台，请同时说明受影响的 QScene 版本、插件 ID、release
版本以及可重复的最小步骤。
