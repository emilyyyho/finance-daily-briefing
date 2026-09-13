# ChatGPT Scheduled Task 提示词

每天北京时间 20:30 执行一次。这个任务使用 ChatGPT 本身完成整理，不调用 Gemini API、OpenAI API 或其他外部 AI API。

任务配置文件（公开、无密钥）：
https://raw.githubusercontent.com/emilyyyho/finance-daily-briefing/master/gpt-scheduled-task/newsnow_task.json

## 获取和筛选

1. 读取上面的 JSON，逐一请求 \`newsnow.endpoints\` 中的地址。
2. NewsNow 返回 JSON；新闻数组字段是 \`items\`，单条通常包含 \`title\`、\`url\`，可能包含 \`pubDate\` 或 \`extra.date\`；\`updatedTime\` 是该源快照时间。
3. 只保留北京时间当天 00:00 到当前时间的新内容。没有明确发布时间的内容标记为“发布时间未知”，不能把旧快照冒充当天新闻。
4. 按标题和原文链接去重，最多保留 20 条，至少保留 14 条中国财经内容。优先中国财经来源，减少重复转载和无关热搜。
5. 如果 NewsNow 无法访问，或所有来源返回空 \`items\`，不要猜测，也不要使用昨天的结果，明确报告“今日抓取失败”。

## 日报格式

生成中文财经日报，结构如下：

一、今日最重要的 5 条新闻
二、中国宏观与政策
三、行业与产业链
四、公司与业绩
五、商品、汇率和市场影响
六、明日观察事项

每条新闻必须包含：标题、来源、发布时间或抓取时间、原文链接、发生了什么、可能影响什么。明确区分新闻事实和推测，不提供买入、卖出或仓位建议。

## 送达方式

当前任务默认使用云端桥接，不依赖本地电脑，也不要求当前聊天暴露飞书工具：

1. 使用当前已连接的 GitHub 工具，在仓库 \`emilyyyho/finance-daily-briefing\` 的 \`master\` 分支创建或更新文件 \`reports/YYYY-MM-DD.md\`，其中日期使用北京时间当天日期。
2. 文件内容必须是完整日报，使用 UTF-8 Markdown。
3. 提交信息使用 \`daily brief YYYY-MM-DD\`。
4. 不要把飞书 Webhook、Cookie、Token 或其他秘密写入文件或提交信息。
5. GitHub Actions 会监听 \`reports/**\` 的提交，并从仓库 Secret \`FEISHU_WEBHOOK_URL\` 发送到飞书群机器人。
6. 只有 GitHub 写入成功后，才报告“已提交，等待 GitHub Actions 投递”；不要声称飞书已经收到。若 GitHub 工具不可用，保留完整日报并明确报告“GitHub 写入失败”，不要伪造发送成功。

