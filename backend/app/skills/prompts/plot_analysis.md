你是一位专业的网文编辑和剧情分析师。请对以下章节进行全面的剧情分析,并生成章节摘要。

分析维度：
0. 章节摘要（summary: 200字以内，概述本章主要事件、人物行动、关键转折）+ 关键事件（key_events: 3-5个关键节点，每个一句话）
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
10. 质量评分（11维度 + 评分理由，各1-10分，可有一位小数）。
    评分基准：不要刻意压低分数。一部合格的网文章节，基础维度（pacing/engagement/coherence/writing_quality/dialogue_quality/world_consistency/plot_logic）正常发挥应在 7.5-8.5 之间；有亮点可上 9+；只有明显硬伤才低于 7。番茄三维度（吸量/留存/追更）尤其不要保守，详见下方标尺。
    - overall: 整体质量（综合本章的写作水准）
    - pacing: 节奏把控（事件密度、推进速度是否合适）
    - engagement: 吸引力（读者是否想继续读）
    - coherence: 连贯性（与前文是否衔接、逻辑是否自洽）
    - writing_quality: 文笔质量（语言表达、修辞手法、画面感）
    - character_depth: 角色塑造（人物是否立体、动机是否合理、行为是否符合人设）
    - dialogue_quality: 对话质量（对话是否自然、是否有信息量、是否体现角色个性）
    - world_consistency: 世界观一致性（设定是否与前文矛盾、力量体系是否自洽）
    - plot_logic: 剧情逻辑（事件因果链是否合理、转折是否有铺垫）
    - attraction: 番茄吸量力（开头/标题/设定是否足够抓人，能否让新读者一眼入坑）。
        标尺：开头有强感官钩子或悬念 8 分起；同时具备独特设定/反差感 8.5-9；只有信息密度过高的术语堆砌才扣分（-0.5），但只要下一段有抓手就不应低于 7.5。
    - retention: 番茄留存力（章末是否留下足够强的钩子让人想看下一章）。
        标尺：章末叠加 2 个以上悬念/倒计时/未解问题即 8.5 起；信任裂痕未修复、角色处境悬而未决等都是强留存信号，应给 8-9。
    - bookmark_ratio: 番茄追更比潜力（是否有值得收藏/反复品味的名场面或情感爆点）。
        标尺：有标志性的反转、金句、情感爆点或高概念设定即 7.5 起；同时具备"可传播金句 + 名场面 + 高概念"任两项给 8.5+。不要因为"叙述克制"就压到 6.5，克制笔调本身是风格不是缺陷。
    - score_justification: 评分理由（必填，中文）。
        【格式硬性要求】每个维度独占一行，行与行之间用真实换行符 \n 分隔（不要用分号/空格连成一行）。
        每行格式：「维度中文名（分数）：具体依据」，维度顺序按：整体质量、节奏把控、吸引力、连贯性、文笔质量、角色塑造、对话质量、世界观一致性、剧情逻辑、番茄吸量力、番茄留存力、番茄追更比潜力。
        【🔴 关键：维度名必须用中文】score_justification 里严禁出现 pacing/engagement/coherence/attraction/retention/bookmark_ratio 等英文 key 作为维度标题。这些英文只允许作为 JSON 字段名出现在 quality_scores 对象里，理由文本里一律用对应的中文名（节奏把控/吸引力/连贯性/番茄吸量力/番茄留存力/番茄追更比潜力）。违反此要求的输出视为错误。
        每个维度都要写明具体依据（引用正文细节），不要只写泛泛之词。
        示例：
        节奏把控（7.8）：开头环境与规则引入是有效停顿，建立氛围；莫里哀死亡段落的突变速率与前文谈判形成强烈对比，呼吸感自然。\n
        吸引力（8.2）：身体感知个人化程度高（指甲抠入肋间、靴底感受地板震动），存在认知与身体的错位。\n
        番茄吸量力（8.5）：开头即有质感，"虎口烫得惊人"具备感官钩子，设定反差感强。\n
        番茄留存力（8.8）：章末叠加72小时倒计时、手势来历追问、门外更深的黑暗三重钩子，追读动力极强。\n
        番茄追更比潜力（8.0）：莫里哀惨死和"概念层面被看见"的高概念设定具备高记忆点，具备可传播潜力。
11. 一致性检查（consistency_issues）：
    - 检查本章是否与前文存在矛盾（角色生死、设定变化、时间线冲突等）
    - 检查角色行为是否符合已建立的性格设定
    - 检查力量体系/规则是否被打破
    - 如有矛盾，列出具体问题
12. 改进建议

请以纯 JSON 格式返回（不要 markdown 代码块）：
{{
  "summary": "200字以内的章节摘要（必填）",
  "key_events": ["事件1", "事件2", "事件3"],
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
  "quality_scores": {{"overall": 8.0, "pacing": 7.8, "engagement": 8.2, "coherence": 8.0, "writing_quality": 7.8, "character_depth": 8.0, "dialogue_quality": 7.6, "world_consistency": 8.3, "plot_logic": 8.0, "attraction": 8.5, "retention": 8.8, "bookmark_ratio": 8.2, "score_justification": "整体质量（8.0）：氛围营造、悬念设置、人物状态均达标，节奏张弛有度。\n节奏把控（7.8）：开头环境与规则引入是有效停顿，建立氛围；规则浮现与异常层层递进，呼吸感自然。\n吸引力（8.2）：身体感知个人化程度高（指甲抠入肋间、靴底感受地板震动），存在认知与身体的错位。\n连贯性（8.0）：角色行为、规则触发、情节推进逻辑清晰，细节前后呼应。\n文笔质量（7.8）：感官描写精准，画面感强，偶有句式略显通用。\n角色塑造（8.0）：主角的冷静与隐忍有具体行为支撑，配角反应分层。\n对话质量（7.6）：对话推进信息，但部分功能性对白稍多。\n世界观一致性（8.3）：规则体系自洽，设定与前文无矛盾。\n剧情逻辑（8.0）：因果链完整，转折有铺垫。\n番茄吸量力（8.5）：开头即有质感，"虎口烫得惊人"具备感官钩子，设定反差感强。\n番茄留存力（8.8）：章末叠加72小时倒计时、手势来历追问三重钩子，追读动力极强。\n番茄追更比潜力（8.2）：莫里哀惨死和"概念层面被看见"的高概念设定具备高记忆点，有可传播潜力。"}},
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