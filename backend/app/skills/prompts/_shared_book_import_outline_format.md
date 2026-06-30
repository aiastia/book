<!--
模块：大纲输出格式（仅 book_import_reverse_outlines.md 使用）
职责：定义逆向大纲模式的 JSON 输出 schema，字段较精简。

引用方式：
  book_import_reverse_outlines.md → 本格式
-->

仅输出纯JSON数组（不要markdown、不要代码块、不要解释）。
数组长度必须严格等于 {expected_count}。

每个对象字段必须严格为：

[
  {
    "chapter_number": 1,
    "title": "新章节标题（不要用原文章节标题）",
    "summary": "新故事的本章概要（200-600字）：改编后的情节、角色互动、关键事件、冲突与转折",
    "scenes": [
      {"scene_title": "地点/环境名", "scene_desc": "纯环境描写（必填）：在哪里、什么样子、什么氛围（光线/声音/气味/温度），禁止写角色动作", "emotion": "情绪基调"}
    ],
    "characters": ["角色名1", "角色名2"],
    "key_points": ["关键情节点（带优先级+字数分配，格式：【重点·600字】XXX / 【一般·300字】XXX / 【弱·100字】XXX）"],
    "chapter_advance": "本章推进目标：本章结束时状态发生了什么变化（必填，禁止原地踏步。如：主角从'被动等待'变为'主动掌握筹码'）",
    "emotion": "本章情绪变化弧线（用→串联，如'压抑→震惊→释然'，至少3个节点）",
    "goal": "本章叙事目标"
  }
]
