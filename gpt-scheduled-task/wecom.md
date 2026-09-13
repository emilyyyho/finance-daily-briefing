# 企业微信投递路径

当前推荐链路是：

\`\`\`text
ChatGPT Scheduled Task
    -> GitHub reports/YYYY-MM-DD.md
    -> GitHub Actions
    -> 飞书群机器人 Webhook
    ->（可选）飞书自动化 HTTP 请求
    -> 企业微信群机器人 Webhook
\`\`\`

## 为什么不把企业微信 CLI 装在电脑上

ChatGPT Scheduled Task 和 GitHub Actions 都能在电脑关机时运行。个人电脑上的 CLI 不能满足这个条件，因此 \`wecom-cli\` 只作为云端部署候选。

候选项目：[WeComTeam/wecom-cli](https://github.com/WeComTeam/wecom-cli)

\`\`\`bash
npm install -g @wecom/cli
npx skills add WeComTeam/wecom-cli -y -g
wecom-cli auth init
wecom-cli auth show
\`\`\`

该 CLI 需要 Node.js 18 以上，并把授权信息保存在本地配置目录。若部署到云端，凭据应放入云端密钥管理，不能写入仓库。

## 飞书转企业微信

1. 在企业微信群中创建群机器人，保存 Webhook。
2. 在飞书自动化中监听日报到达或写入专用多维表格记录。
3. 用 HTTP 请求动作调用企业微信群机器人 Webhook。
4. 企业微信失败时，不删除 GitHub 报告，也不影响飞书主投递。

企业微信 Webhook 仍属于敏感凭据，不要提交到仓库、任务提示词或公开文档。
