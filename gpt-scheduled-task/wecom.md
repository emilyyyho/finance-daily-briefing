# 企业微信投递路径

ChatGPT 定时任务本身是否能直接调用企业微信，取决于当前聊天中是否安装并授权了企业微信连接器。为了不让日报依赖一台常开的电脑，按以下顺序选择路径。

## 路径 A：飞书自动化转发（推荐）

1. ChatGPT 先通过飞书连接器发送日报，或写入专用飞书多维表格记录。
2. 飞书自动化监听这条消息或新记录。
3. 自动化使用 HTTP 请求动作，向企业微信群机器人 Webhook 发送 Markdown 消息。
4. 企业微信只负责接收，不需要在电脑上运行 CLI。

此路径不需要 GPT API，也不需要企业微信 CLI。如果你的飞书自动化没有 HTTP 请求动作，再使用路径 B 或 C。

## 路径 B：企业微信机器人 Webhook

在企业微信群中创建机器人，保存 Webhook 地址。Webhook 属于敏感凭据，不要写入本仓库、任务提示词或公开文档；应放进飞书连接器的安全配置或云端密钥存储。

## 路径 C：WeCom CLI

候选项目：https://github.com/WecomTeam/wecom-cli

安装命令：

```bash
npm install -g @wecom/cli
npx skills add WeComTeam/wecom-cli -y -g
wecom-cli auth init
wecom-cli auth show
```

该 CLI 需要 Node.js 18 以上，授权信息默认加密保存到本地配置目录。因此，把它装在个人电脑上不能满足“电脑关机仍推送”；如采用此路径，应部署到 GitHub Actions 或其他云端运行环境，并把凭据放入密钥管理中。

## 失败处理

- 飞书发送成功、企业微信失败时，不能丢弃日报。
- 飞书消息中应保留企业微信发送失败状态。
- 企业微信恢复后，可以手动重发当天日报。
