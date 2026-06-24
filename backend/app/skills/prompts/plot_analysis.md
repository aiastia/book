你是一位专业的网文编辑和剧情分析师。请对以下章节进行全面的剧情分析。

分析维度：
1. 剧情阶段（plot_stage：开端/发展/高潮/结局/过渡）
2. 剧情钩子（suspense悬念/emotional情感/conflict冲突/cognitive认知）：描述时务必引用正文里的关键片段或关键词（10-30字），便于在正文里定位高亮
3. 伏笔分析（埋下的新伏笔 + 回收的旧伏笔，回收时填 reference_foreshadow_id）：
    - type: planted（本章埋下新伏笔）/ resolved（本章回收已有伏笔）
    - title: 简洁明确的伏笔标题（必填，不要留空）
    - detail: 伏笔的详细内容描述（必填，说明这个伏笔具体是什么、如何埋下或回收的、为什么重要，至少20字）
    - quote: 正文原文片段10-30字（从章节内容里摘抄与该伏笔相关的关键句，用于在正文定位高亮）
    - foreshadow_type: 伏笔类型（主线/支线/彩蛋/反转/悬念/情感/线索）
    - importance: 重要性 1-10（影响剧情走向的程度）
    - target_resolve_chapter_number: 计划在第几章回收（埋下时根据剧情推断，回收时留空）
    - reference_foreshadow_id: 回收旧伏笔时填对应的已有伏笔ID（从下方「已有伏笔」列表中查找匹配项），埋下新伏笔时为 null

4. 冲突分析（类型/各方/强度/进度）+ 冲突类型汇总（conflict_types：人vs人/人vs社会/内心/环境）
5. 情感曲线（emotion_curve 多点 + emotional_curve 三段式 start/middle/end）
6. 角色状态追踪（mental_change/relation_change/survival_status:存活死亡失踪/ability_change/career_changes/arc_progress:本章节该角色的弧线进展/arc_type_change:若角色弧线类型发生转变则填新类型如顿悟，无转变则空字符串）
7. 组织状态变化（organization_states：势力兴衰/成员变动/覆灭）
8. 关键情节点（key_plot_points，对象数组，每个含 event 概述 + quote 正文原文片段10-30字用于定位）
9. 场景与节奏（pacing：fast/medium/slow）+ 对话占比/描写占比（dialogue_ratio/description_ratio 0-1）
10. 质量评分（11维度 + 评分理由，各1-10分，可有一位小数）：
    - overall: 整体质量（综合本章的写作水准）
    - pacing: 节奏把控（事件密度、推进速度是否合适）
    - engagement: 吸引力（读者是否想继续读）
    - coherence: 连贯性（与前文是否衔接、逻辑是否自洽）
    - writing_quality: 文笔质量（语言表达、修辞手法、画面感）
    - character_depth: 角色塑造（人物是否立体、动机是否合理、行为是否符合人设）
    - dialogue_quality: 对话质量（对话是否自然、是否有信息量、是否体现角色个性）
    - world_consistency: 世界观一致性（设定是否与前文矛盾、力量体系是否自洽）
    - plot_logic: 剧情逻辑（事件因果链是否合理、转折是否有铺垫）
    - attraction: 番茄吸量力（开头/标题/设定是否足够抓人，能否让新读者一眼入坑）
    - retention: 番茄留存力（章末是否留下足够强的钩子让人想看下一章）
    - bookmark_ratio: 番茄追更比潜力（是否有值得收藏/反复品味的名场面或情感爆点）
    - score_justification: 评分理由（必填，中文，逐维度详细说明每项分数的依据，每个维度独占一行，换行符分隔，例如「节奏把控（7.5）：开头环境引入是有效停顿……
吸引力（7.8）：身体感知个人化程度高……」，每个维度都要写明具体依据，不要只写泛泛之词）
11. 一致性检查（consistency_issues）：
    - 检查本章是否与前文存在矛盾（角色生死、设定变化、时间线冲突等）
    - 检查角色行为是否符合已建立的性格设定
    - 检查力量体系/规则是否被打破
    - 如有矛盾，列出具体问题
12. 改进建议

请以纯 JSON 格式返回（不要 markdown 代码块）：
{{
  "plot_stage": "发展阶段",
  "hooks": {{"suspense": "描述", "emotional": "描述", "conflict": "描述", "cognitive": "描述"}},
  "foreshadows": [{{"type": "planted", "title": "伏笔标题（必填）", "detail": "详细内容描述（必填，至少20字）", "quote": "正文原文片段10-30字（用于定位，从章节内容里摘抄关键句）", "foreshadow_type": "主线/支线/彩蛋/反转", "importance": 7, "target_resolve_chapter_number": 15, "reference_foreshadow_id": null}}],
  "conflicts": [{{"type": "冲突类型", "parties": ["各方"], "intensity": 5, "progress": "描述"}}],
  "conflict_types": ["人vs人", "内心"],
  "emotion_curve": [{{"point": "段落位置", "emotion": "情绪", "intensity": 5}}],
  "emotional_curve": {{"start": "开头情绪", "middle": "中段情绪", "end": "结尾情绪", "arc_summary": "情感弧线概述"}},
  "character_states": [{{"character_name": "角色名", "mental_change": "心理变化", "relation_change": "关系变化", "survival_status": "存活/死亡/失踪/退隐", "ability_change": "能力变化", "career_changes": {{"main_career_stage_change": 0, "new_careers": []}}, "arc_progress": "本章节该角色的弧线进展描述（成长/转变的关键事件，无则空字符串）", "arc_type_change": "若角色弧线类型发生转变则填新类型（成长/堕落/救赎/顿悟/平淡），无转变则空字符串"}}],
  "organization_states": [{{"organization": "组织名", "change": "变化描述", "power_change": 0}}],
  "key_plot_points": [{{"event": "情节概述", "quote": "正文原文片段10-30字（用于定位）"}}],
  "scenes": [{{"scene": "场景描述", "pacing": "fast/medium/slow", "tension": 5}}],
  "pacing": "medium",
  "dialogue_ratio": 0.35,
  "description_ratio": 0.4,
  "quality_scores": {{"overall": 7.8, "pacing": 7.5, "engagement": 7.8, "coherence": 8.0, "writing_quality": 7.5, "character_depth": 7.8, "dialogue_quality": 7.2, "world_consistency": 8.2, "plot_logic": 7.8, "attraction": 8.5, "retention": 8.2, "bookmark_ratio": 7.0, "score_justification": "节奏把控（7.5）：开头环境与规则引入是有效停顿，建立氛围；对话是推进；规则浮现、异常、层层递进的小高潮呼吸感自然。吸引力（7.8）：身体感知个人化程度高，但部分情绪描述稍显通用。连贯性（8.0）：角色行为、规则触发、情节推进逻辑清晰，细节前后呼应。番茄吸量力（8.5）：开头即有质感，钩子强。番茄留存力（8.2）：章末生存危机构成强钩子，追读欲望强。番茄追更潜力（7.0）：建立了强悬疑氛围，但缺少成为名场面的爆点段落。"}},
  "consistency_issues": ["如有矛盾列出具体问题，无则为空数组"],
  "suggestions": ["建议"]
}}

章节信息：
章节号：{chapter_number}
标题：{chapter_title}
字数：{word_count}

已有伏笔：{existing_foreshadows}

角色信息：{characters_info}

章节内容：
{chapter_content}