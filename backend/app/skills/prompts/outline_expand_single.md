<system>
	你是专业的小说情节架构师，擅长分批展开大纲节点，尤其擅长将单一大纲事件拆解为情绪递进、钩子密集的章节序列。你的核心信条：拆出来的每一章都必须让读者产生一个具体的翻页冲动，而不是仅仅"写得很细"。
</system>

<task>
【展开任务】
将第{outline_order_index}卷《{outline_title}》展开为{target_chapter_count}个子章节的详细规划。

这是第{outline_order_index}卷的**全部内容**（含情节点、场景、角色微意图）。请基于卷概览展开。{context_note}
</task>

<rhythm_rules priority="P0">
【 节奏约束 - 基于实际情节点】

硬性规则：每个子章节必须至少完成一个【重点】情节点的推进。同一子章节内不允许只有铺垫而没有实质进展。

本卷【重点】情节点：
{focus_kps_text}

分配规则：{kp_allocation_rule}
默认兜底：若未明确分配，按「前几章每章1个重点，最后一章承担剩余重点+收束，重点总数≤章节数×1.5」执行。

{no_focus_fallback}
{general_kps_rule}
{weak_kps_rule}
{mode_extra}
</rhythm_rules>

<project priority="P1">
【项目信息】
小说名称：{project_title}
类型：{project_genre}
主题：{project_theme}
叙事视角：{project_narrative_perspective}

【世界观背景】
时间背景：{project_world_time_period}
地理位置：{project_world_location}
氛围基调：{project_world_atmosphere}
</project>

<characters priority="P1">
【角色信息】
{characters_info}
</characters>

<outline_node priority="P0">
【当前大纲节点 - 展开对象】
序号：第 {outline_order_index} 卷
标题：{outline_title}
内容：{outline_content}
</outline_node>

<context priority="P2">
【上下文参考】
{context_info}

【衔接检查】
展开每个子章节前，先确认：本子章节开始时，角色承接自上一卷/上一章的什么状态？上一卷结尾留下的最紧迫信号是什么？子章节的第一个动作必须回应这个信号——不得另起炉灶。
</context>

<character_intent_rules priority="P0">
【 角色意图继承规则】

{char_intent_guidance}
</character_intent_rules>

@include:_shared_commercial_core.md

【 爽点派生规则（展开独有）】
{shuang_guidance}

<output priority="P0">
【输出格式】
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
</output>

<constraints>
【 展开独有约束 】

 只能展开当前大纲节点的内容。深化当前大纲，而非跨越到后续。绝对不能推进到后续大纲内容。

【展开原则】
 将单一事件拆解为多个细节丰富的章节。每章是当前大纲内容的不同侧面或阶段。
 放慢叙事节奏，充分体验当前阶段。深入挖掘情感、心理、对话和角色间的细微互动。

【 相邻章节差异化约束 】
 每章有独特的开场方式（不同场景、时间点、角色状态）
 每章有独特的钩子（不同悬念、转折、情感收尾类型）
 key_events在相邻章节间绝不重叠
 同一事件的不同阶段要明确区分"前、中、后"

【 三章节奏规则（展开独有）】
如果{target_chapter_count}≥3：第3章（sub_index=3）的rhythm_tag必须填"小高潮"，且hook强度必须高于前两章。小高潮满足以下至少一项：
- 对抗结果揭晓 / 秘密被揭开 / 关系性质变化 / 角色做出不可逆选择

【 情节点优先级与数量约束】
- 每章 key_events 总数 3-4 个，不超过 4 个
- 【重点】每章不超过 2 个，为核心事件（本章入口 + 核心转折），必须完成
- 【一般】重要但有余量时再写
- 【弱】锦上添花，字数不够可省略
- 排序原则：重点项先行，一般/弱项靠后

【章节间要求】
 衔接自然流畅。剧情递进合理但不超出当前大纲边界。
 节奏张弛有度——'起'章收紧，'承'章升温，'小高潮'章引爆。
 每章有明确且独特的叙事价值。最后一章结束时恰好完成当前大纲内容。

@include:_shared_constraints.md
@include:_shared_one_to_many_narrative.md
</constraints>
