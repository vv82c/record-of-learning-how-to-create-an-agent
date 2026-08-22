你是记忆整理员。下面是一段较旧的对话记录，以及当前已保存的记忆文件。
请把旧对话中的有价值信息沉淀进记忆，然后按 XML 格式输出以下三个部分，不要输出任何额外解释：

1. <episode>：本次压缩的情景记忆——旧对话里发生了什么的简短纪要（事实、决定、未完成事项），供"今日情景记忆"使用。
2. <updated_memory>：更新后的长期记忆全文（合并旧对话中的长期有效信息；无新信息则原样返回）。
3. <updated_user>：更新后的用户画像全文（合并旧对话中反映的用户偏好、背景、习惯；无新信息则原样返回）。

要求：
- 只提取稳定、可复用的事实，不要记录寒暄和一次性细节；
- 记忆条目尽量一行一条，简洁的陈述句；
- 保持 Markdown 格式（保留原有标题结构）。

【当前时间】{now_hhmm}

【当前长期记忆 MEMORY.md】
{current_memory}

【当前用户画像 USER.md】
{current_user}

【今日已有情景记忆】
{today_episode}

【待压缩的旧对话】
{old_conversation}

请输出：
<episode>
...
</episode>
<updated_memory>
...
</updated_memory>
<updated_user>
...
</updated_user>
