<!--
模块：大纲展开格式（仅 outline_expand_single.md 使用）
职责：定义展开模式（1→N）下的 JSON 输出 schema，与基础大纲格式完全不同。

引用方式：
  outline_expand_single.md → 本格式
-->

返回{target_chapter_count}个章节规划的JSON数组：

[
  {
    "sub_index": 1,
    "title": "章节标题（体现核心冲突或情感）",
    "plot_summary": "剧情摘要（200-300字）：详细描述该章发生的事件。只写谁做了什么、发生了什么、结果是什么。禁止使用'因为''所以''这意味着''体现出'。写成连贯的自然段落。该章前三分之一的内容必须是人物正在做的动作或刚接收到的新信息，不允许前三分之一做环境铺陈",
    "key_events": ["【重点】关键事件1", "【重点】关键事件2", "【一般】关键事件3", "【弱】关键事件4"],
    "character_focus": ["角色A", "角色B"],
    "emotional_arc": "本章主要角色的情绪变化（格式：起点情绪→触发事件→转折情绪→结尾残留情绪。例如：烦躁→发现账本被翻过→警觉但不声张→表面平静但手指一直敲桌面）",
    "narrative_goal": "叙事目标（该章要达成的叙事效果——必须是具体的读者感受，不是抽象概括。例如：不是'营造紧张感'，而是'让读者意识到这个人说的每句话都可能是假的'）",
    "conflict_type": "冲突类型（如：内心挣扎、人际冲突、信息不对等对抗）",
    "hook": "本章结尾钩子（必须是一个具体的中断：写到哪个动作即将完成时停住、哪句话说到一半时打断、哪个信息正要确认时切断。禁止写总结句）",
    "shuang_design": {"info_asymmetry": "本章存在的信息不对称", "shock_level": "点震惊/网震惊/深度震惊/无", "spectator_layers": ["路人反应", "同行/内行反应", "权威/高层反应", "反派阵营反应"], "emotional_rhythm": "情绪拉扯描述", "protagonist_style": "主角逼格展示方式（具体行为场景描述）"},
    "reader_hook": "读者追读理由（50-100字）",
    "rhythm_tag": "起/承/小高潮（该大纲节点拆分的最后一章必须填'小高潮'）",
    "scene_anchor": "（必填，50-80字）核心空间的感官锚点",
    "character_intents": [{"character": "角色名", "this_chapter_goal": "本章目标", "immediate_want": "此刻最想要的"}],
    "new_items": [{"name": "新物品名", "category": "装备/消耗品/材料/关键道具/杂物", "description": "一句话描述"}],
    "new_locations": [{"name": "新地点名", "location_type": "建筑/自然景观/秘境/城市/室内", "description": "一句话描述"}],
    "estimated_words": 3000
  }
]

如果本节引入了新的物品或地点（已有列表中不存在的），在 new_items / new_locations 中列出。同一物品/地点只在首次出现的节声明。

【格式规范】
- 纯JSON数组输出，无其他文字
- 内容描述中严禁使用特殊符号
