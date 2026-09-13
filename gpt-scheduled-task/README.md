# GPT 定时财经日报

这组配置把 Cha
tGPT Scheduled Tasks 作为每日财经日报
的编排器，并用 GitHub Actions 作为�
�端投递桥接：

\`\`\`text
ChatGPT 定�
�任务
    -> NewsNow 当日数据
    -> �
�期过滤与标题去重
    -> GPT 事实�
�理与主题分析
    -> GitHub 连接器�
�交 reports/YYYY-MM-DD.md
    -> GitHub Acti
ons
    -> 飞书群机器人 Webhook
\`\`\`


## 目标

- 每天北京时间 20:30 运行
一次。
- 只处理北京时间当天 00:00
 到运行时刻的新内容。
- NewsNow 是
主要信息源。
- 不调用 Gemini API 或
 GPT API。
- 电脑关机时仍然可以运�
�� ChatGPT 网页端任务和 GitHub Actions�
��
- Scheduled Task 不需要暴露飞书连�
��器；飞书由 GitHub Actions 云端发送
。

## 文件

- \`task-prompt.md\`：可直
接粘贴到 ChatGPT Scheduled Task 的任务
说明。
- \`newsnow_task.json\`：无密钥
的运行参数模板。
- \`validate_config.
py\`：本地和 GitHub Actions 使用的配�
��校验。
- \`send_feishu.py\`：用仓库 
Secret 调用飞书群机器人 Webhook 的�
�依赖脚本。
- \`wecom.md\`：企业微�
� CLI 和飞书自动化桥接路径。

## �
��次性配置

1. 在飞书目标群中添�
�“群机器人”，复制 Webhook 地址�
�
2. 在 GitHub 仓库的 **Settings → Secr
ets and variables → Actions** 中新建 Sec
ret：
   - Name：\`FEISHU_WEBHOOK_URL\`
   
- Secret：粘贴 Webhook 地址
3. 不要把
 Webhook 地址写进 JSON、Markdown、任�
�提示词或公开 Issue。
4. 确认 ChatGP
T Scheduled Task 所在聊天能使用 GitHub
 连接器。飞书连接器不是必需的�
�
5. 创建定时任务时粘贴 \`task-promp
t.md\`，时区选 \`Asia/Shanghai\`，时间
选 20:30。

## 测试

1. 在 GitHub 网页
直接新建 \`reports/test.md\`，内容写�
��财经日报连接测试，发送时间：�
��在。”并提交到 \`master\`。
2. 打�
�� **Actions → Deliver daily report to Feis
hu**，等待工作流运行。
3. 检查飞�
��群是否收到消息。若失败，先检�
�� Secret 名称是否严格为 \`FEISHU_WEBH
OOK_URL\`。
4. 也可以在该工作流的 *
*Run workflow** 中填写一个已存在的 \
`reports/*.md\` 文件路径进行重发。
5
. 日常任务写入 \`reports/YYYY-MM-DD.md\
` 后，推送会自动触发，无需电脑�
��机。

## 安全边界

不要把 NewsNow 
私钥、飞书 Webhook、企业微信 Secret
、Cookie 或任何网页登录凭据提交�
�此仓库。任务只提交日报正文和�
�源链接。

## 验收标准

- 任务每�
�只生成一份日报。
- 日报中的新�
�属于北京时间当天，或明确标注�
�发布时间未知”。
- 每条内容都�
�来源和原文链接。
- NewsNow 无法访
问时不会使用昨天的旧数据。
- Git
Hub 提交成功后，Actions 能通过 Secre
t 将日报送到飞书。
- 企业微信转�
��失败时，日报仍保留在 GitHub 和�
�书链路中。


