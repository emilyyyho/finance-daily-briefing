# ChatGPT Scheduled Task 提示词

将下面的正文粘贴到 ChatGPT 网页端的 Scheduled Task。

任务配置文件（公开、无密钥）：
https://raw.githubusercontent.com/emilyyyho/finance-daily-briefing/master/gpt-scheduled-task/newsnow_task.json

请先读取该 JSON，逐一请求 newsnow.endpoints 中的地址。NewsNow 返回 JSON，新闻数组字段是 items，单条通常包含 title、url，可能包含 pubDate 或 extra.date；updatedTime 是该源快照时间。

```text
每天北京时间 20:30 执行一次。

只保留北京时间当天 00:00 到当前时间的新内容。
如果内容没有明确发布时间，标记为“发布时间未知”。
按标题和原文链接去重，最多保留 20 条，至少保留 14 条中国财经内容。
优先保留中国财经来源，减少重复转载和无关热搜。
不使用昨天的旧内容冒充当天新闻。
不调用 Gemini API、OpenAI API 或其他外部 AI API；直接使用当前 ChatGPT 任务本身完成整理。
如果 NewsNow 无法访问，或所有源都返回空 items，不要猜测，也不要使用旧结果，报告“今日抓取失败”。

请生成中文财经日报，结构如下：
一、今日最重要的 5 条新闻
二、中国宏观与政策
三、行业与产业链
四、公司与业绩
五、商品、汇率和市场影响
六、明日观察事项

每条新闻必须包含：标题、来源、发布时间或抓取时间、原文链接、发生了什么、可能影响什么。
请明确区分新闻事实和推测，不提供买入、卖出或仓位建议。

日报生成后，使用当前已连接的飞书工具发送到指定的财经日报群。
如果飞书发送失败，保留完整日报并明确报告发送失败原因。
```

## 连接测试提示词

在创建定时任务前，先在普通聊天中运行：

```text
请使用当前已连接的飞书工具，向我的测试群发送：
“财经日报连接测试，发送时间：现在。”
```
