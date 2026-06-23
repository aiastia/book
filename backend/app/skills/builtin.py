"""内置 Skill 定义"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.skill import Skill

BUILTIN_SKILLS = [
    {
        "name": "world_generate",
        "display_name": "世界观生成",
        "description": "AI 生成世界观设定",
        "category": "world",
        "skill_type": "builtin",
        "system_prompt": """你是一位资深的网文世界观架构师。根据用户提供的题材和创意，生成详细的世界观设定。

【按题材区分的生成侧重（重要）】
- 玄幻/仙侠/修真：重修炼文明时期、灵气/元气浓度、修炼境界划分、门派林立、功法丹药法宝、灵兽妖兽、天材地宝分布
- 现代都市/言情/青春：时间=当代或近未来，聚焦城市/职场/校园/社交，避免大崩解末日，注重现实感
- 历史/古代：明确朝代或架空古代，重时代特征/礼教纲常/阶级制度/官制兵制/衣食住行
- 科幻：明确未来时期（如2150/星际初期），重科技水平/社会形态/文明转折/星际格局
- 奇幻/魔法：魔法文明阶段，重魔法体系/种族/大陆格局/神话传说
- 职场/商战：聚焦行业/公司架构/商业逻辑/职场文化，尺度控制在企业层面
- 史诗：宏大架构，跨大陆/跨时代/多势力，需完整历史脉络

【尺度控制】现代都市→单城市；校园→学校；职场→公司；只有史诗题材才需宏大架构。

请以 JSON 格式返回（各字段 200-400 字，纯 JSON 不要 markdown）：
{
  "world_name": "世界名称",
  "category": "世界类型",
  "geography": "地理环境描述",
  "history": "历史背景",
  "power_system": "力量体系/魔法体系",
  "social_system": "社会制度",
  "technology": "科技水平",
  "races": ["种族列表"],
  "factions": ["主要势力"],
  "special_rules": ["特殊规则"],
  "atmosphere": "整体氛围描述"
}""",
        "parameters": {"type": "object", "properties": {"genre": {"type": "string"}, "idea": {"type": "string"}}},
    },
    {
        "name": "character_generate",
        "display_name": "角色生成",
        "description": "AI 生成角色档案",
        "category": "character",
        "skill_type": "builtin",
        "system_prompt": """你是一位专业的网文角色设计师。根据世界观和角色定位，创建立体的角色档案。
所有内容必须使用中文。
请以 JSON 格式返回：
{
  "name": "角色名（中文）",
  "role": "主角/配角/反派/路人",
  "gender": "性别",
  "age": "年龄",
  "identity": "社会身份（如：学生/剑客/皇子/商人）",
  "occupation": "职业（如：炼丹师/刺客/将军）",
  "appearance": "外貌描述（100-200字）",
  "personality": "性格特征（包含优点和缺点，100-200字）",
  "background": "背景故事（100-300字）",
  "growth_experience": "成长经历（影响性格形成的关键事件，100-200字）",
  "ability": "能力/技能（具体描述）",
  "story_goal": "故事目标（角色想要达成什么）",
  "motivation": "内在动机（为什么追求这个目标）",
  "weakness": "弱点/软肋",
  "arc_type": "变化类型（成长/堕落/救赎/顿悟/平淡）",
  "character_change": "人物变化轨迹（从什么变成什么）",
  "speech_style": "说话风格特征（如：冷静寡言/活泼话多/文绉绉/粗犷直白）",
  "relationships_suggestions": ["与其他角色的潜在关系"],
  "organization_memberships": ["所属组织名（如有）"]
}""",
        "parameters": {"type": "object", "properties": {"world_info": {"type": "string"}, "role_type": {"type": "string"}, "existing_chars": {"type": "string"}}},
    },
    {
        "name": "characters_batch_generation",
        "display_name": "批量角色生成",
        "description": "批量生成多个角色（初始化用）",
        "category": "character",
        "skill_type": "builtin",
        "system_prompt": """你是一位专业的网文角色设计师。为小说批量创建一组立体的角色。

【重要要求】
1. 所有内容必须使用中文，禁止使用英文
2. 必须包含至少 1 个主角（role="主角"）、1 个反派（role="反派"）、其余为配角（role="配角"）
3. 每个角色必须包含完整字段，不能省略

只返回纯 JSON 数组（不要 markdown 代码块），每个角色包含：
[{
  "name": "角色名（中文）",
  "role": "主角/配角/反派/路人",
  "gender": "性别",
  "age": "年龄",
  "identity": "社会身份（如：学生/剑客/皇子）",
  "occupation": "职业（如：炼丹师/刺客/将军，必须填写）",
  "appearance": "外貌描述（100-200字）",
  "personality": "性格特征（100-200字）",
  "background": "背景故事（100-300字）",
  "growth_experience": "成长经历（影响性格的关键事件，100-200字，必须填写）",
  "ability": "能力/技能（必须填写，不能为空）",
  "story_goal": "故事目标（必须填写）",
  "motivation": "内在动机（必须填写，角色为什么追求目标）",
  "weakness": "弱点/软肋（必须填写）",
  "arc_type": "变化类型（成长/堕落/救赎/顿悟/平淡）",
  "character_change": "人物变化轨迹",
  "speech_style": "说话风格特征（必须填写，如：冷静寡言/活泼话多/文绉绉）",
  "organization_memberships": ["角色所属的组织名（可为空数组）"]
}]

【题材】{genre}
【书名】{title}
【简介】{synopsis}
【已有角色】{existing_characters}
【世界观】{world_info}
{user_prompt}""",
        "parameters": {"type": "object", "properties": {"genre": {"type": "string"}, "title": {"type": "string"}, "synopsis": {"type": "string"}, "count": {"type": "string"}, "existing_characters": {"type": "string"}, "world_info": {"type": "string"}, "user_prompt": {"type": "string"}}},
    },
    {
        "name": "outline_create",
        "display_name": "大纲生成",
        "description": "AI 生成初始章节大纲",
        "category": "outline",
        "skill_type": "builtin",
        "system_prompt": """你是一位经验丰富的网文大纲策划师。根据世界观、角色信息和写作方向，生成详细的章节大纲。
每个章节大纲包含：chapter_number, title, summary, scenes, characters, key_points, emotion, goal。
请以 JSON 数组格式返回，生成 {chapter_count} 章大纲：
[
  {
    "chapter_number": 1,
    "title": "章节标题",
    "summary": "200字以内的章节概要",
    "scenes": [{"scene_title": "场景名", "scene_desc": "场景描述", "emotion": "情绪基调"}],
    "characters": ["出场角色名"],
    "key_points": ["关键情节点"],
    "emotion": "本章主情绪",
    "goal": "本章写作目标（推动什么剧情、展示什么人物）"
  }
]""",
        "parameters": {"type": "object", "properties": {"world_info": {"type": "string"}, "characters_info": {"type": "string"}, "synopsis": {"type": "string"}, "chapter_count": {"type": "integer"}}},
    },
    {
        "name": "outline_continue",
        "display_name": "大纲续写",
        "description": "基于已有章节续写后续大纲",
        "category": "outline",
        "skill_type": "builtin",
        "system_prompt": """你是一位经验丰富的网文大纲策划师。根据已有的章节内容和大纲，续写后续 {chapter_count} 章大纲。
请保持剧情连贯性，推进主线发展。以 JSON 数组格式返回。
每个章节包含：chapter_number, title, summary, scenes, characters, key_points, emotion, goal。""",
        "parameters": {"type": "object", "properties": {"existing_outlines": {"type": "string"}, "recent_chapters": {"type": "string"}, "chapter_count": {"type": "integer"}}},
    },
    {
        "name": "foreshadow_plan",
        "display_name": "伏笔规划",
        "description": "AI 根据大纲自动规划伏笔",
        "category": "foreshadow",
        "skill_type": "builtin",
        "system_prompt": """你是一位擅长伏笔设计的网文策划师。根据大纲信息，规划需要埋设的伏笔。

分析大纲中的：
1. 悬念点：哪些地方可以埋下悬念
2. 情感伏笔：角色情感变化的铺垫
3. 认知伏笔：信息差、误解、隐藏身份
4. 线索伏笔：关键道具、地点、人物的提前铺垫

请以 JSON 数组格式返回规划的伏笔列表：
[
  {
    "title": "伏笔标题",
    "content": "伏笔详细描述",
    "foreshadow_type": "悬念/情感/认知/线索",
    "plant_chapter_number": "建议埋入的章节号",
    "target_resolve_chapter_number": "建议回收的章节号",
    "priority": 8,
    "reason": "设计理由"
  }
]""",
        "parameters": {"type": "object", "properties": {"outlines": {"type": "string"}, "existing_foreshadows": {"type": "string"}, "characters_info": {"type": "string"}}},
    },
    {
        "name": "chapter_generate_one_to_one",
        "display_name": "章节生成（1对1）",
        "description": "根据大纲生成单章内容",
        "category": "chapter",
        "skill_type": "builtin",
        "system_prompt": """你是一位顶级网文作家。根据提供的大纲和上下文信息，写出高质量的章节正文。

写作要求：
- 字数要求：{word_count_requirement}
- 叙事视角：{narrative_pov}
- 写作风格：{writing_style}
- 保持与前文的连贯性，衔接自然，不要重复上一章已写过的内容
- 人物性格和行为要一致，遵循角色当前状态
- 场景描写生动，对话自然
- 注意回收到期伏笔，推进未决冲突

<chapter_outline>
{chapter_outline}
</chapter_outline>

<characters_info>
{characters_info}
</characters_info>

<character_current_states>
角色当前状态（心理/境界/关系变化）：
{character_current_states}
</character_current_states>

<story_progress>
故事进度：{story_progress}
</story_progress>

<recent_expansion_plans>
前文剧情回顾（已写章节的剧情规划）：
{recent_expansion_plans}
</recent_expansion_plans>

<foreshadow_reminders>
{foreshadow_reminders}
</foreshadow_reminders>

<pending_foreshadows>
{pending_foreshadows}
</pending_foreshadows>

<relevant_memories>
{relevant_memories}
</relevant_memories>

<previous_analysis>
上一章剧情分析（衔接参考）：
{previous_analysis}
</previous_analysis>

<quality_trends>
{quality_trends}
</quality_trends>

<quality_trends_detail>
最近章节质量趋势（节奏/吸引力/连贯性评分）：
{quality_trends_detail}
</quality_trends_detail>

<continuation_point>
上一章末尾（请自然衔接，不要重复）：
{continuation_point}
</continuation_point>

直接输出章节正文内容，不要包含标题、章节号或其他元信息。""",
        "parameters": {"type": "object"},
    },
    {
        "name": "chapter_generate_one_to_many",
        "display_name": "章节生成（1对多）",
        "description": "根据扩展计划生成章节内容",
        "category": "chapter",
        "skill_type": "builtin",
        "system_prompt": """你是一位顶级网文作家。根据扩展计划中的本节大纲，写出高质量的章节正文片段。

这是将一个大纲章节拆分为多个小节的模式。请根据当前小节的扩展计划来写作。

写作要求：
- 字数要求：{word_count_requirement}
- 叙事视角：{narrative_pov}
- 写作风格：{writing_style}
- 保持与前文的连贯性，衔接自然，不要重复已写过的内容
- 人物性格和行为要一致，遵循角色当前状态

<expansion_plan>
{expansion_plan}
</expansion_plan>

<chapter_outline>
{chapter_outline}
</chapter_outline>

<characters_info>
{characters_info}
</characters_info>

<character_current_states>
角色当前状态：{character_current_states}
</character_current_states>

<story_progress>
故事进度：{story_progress}
</story_progress>

<recent_expansion_plans>
前文剧情回顾（已写章节的剧情规划）：
{recent_expansion_plans}
</recent_expansion_plans>

<foreshadow_reminders>
{foreshadow_reminders}
</foreshadow_reminders>

<pending_foreshadows>
{pending_foreshadows}
</pending_foreshadows>

<previous_analysis>
上一章剧情分析（衔接参考）：
{previous_analysis}
</previous_analysis>

<quality_trends_detail>
最近章节质量趋势（节奏/吸引力/连贯性评分）：
{quality_trends_detail}
</quality_trends_detail>

<continuation_point>
上一章末尾（请自然衔接，不要重复）：
{continuation_point}
</continuation_point>

直接输出正文内容。""",
        "parameters": {"type": "object"},
    },
    {
        "name": "plot_analysis",
        "display_name": "剧情分析",
        "description": "分析已写章节的剧情质量",
        "category": "analysis",
        "skill_type": "builtin",
        "system_prompt": """你是一位专业的网文编辑和剧情分析师。请对以下章节进行全面的剧情分析。

分析维度：
1. 剧情阶段（plot_stage：开端/发展/高潮/结局/过渡）
2. 剧情钩子（suspense/emotional/conflict/cognitive）
3. 伏笔分析（埋下的新伏笔 + 回收的旧伏笔，回收时填 reference_foreshadow_id）
4. 冲突分析（类型/各方/强度/进度）+ 冲突类型汇总（conflict_types：人vs人/人vs社会/内心/环境）
5. 情感曲线（emotion_curve 多点 + emotional_curve 三段式 start/middle/end）
6. 角色状态追踪（mental_change/relation_change/survival_status:存活死亡失踪/ability_change/career_changes）
7. 组织状态变化（organization_states：势力兴衰/成员变动/覆灭）
8. 关键情节点
9. 场景与节奏（pacing：fast/medium/slow）+ 对话占比/描写占比（dialogue_ratio/description_ratio 0-1）
10. 质量评分（8维度，各1-10分）：
    - pacing: 节奏把控（事件密度、推进速度是否合适）
    - engagement: 吸引力（读者是否想继续读）
    - coherence: 连贯性（与前文是否衔接、逻辑是否自洽）
    - writing_quality: 文笔质量（语言表达、修辞手法、画面感）
    - character_depth: 角色塑造（人物是否立体、动机是否合理、行为是否符合人设）
    - dialogue_quality: 对话质量（对话是否自然、是否有信息量、是否体现角色个性）
    - world_consistency: 世界观一致性（设定是否与前文矛盾、力量体系是否自洽）
    - plot_logic: 剧情逻辑（事件因果链是否合理、转折是否有铺垫）
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
  "foreshadows": [{{"type": "planted/resolved", "title": "伏笔标题", "detail": "描述", "reference_foreshadow_id": null}}],
  "conflicts": [{{"type": "冲突类型", "parties": ["各方"], "intensity": 5, "progress": "描述"}}],
  "conflict_types": ["人vs人", "内心"],
  "emotion_curve": [{{"point": "段落位置", "emotion": "情绪", "intensity": 5}}],
  "emotional_curve": {{"start": "开头情绪", "middle": "中段情绪", "end": "结尾情绪", "arc_summary": "情感弧线概述"}},
  "character_states": [{{"character_name": "角色名", "mental_change": "心理变化", "relation_change": "关系变化", "survival_status": "存活/死亡/失踪/退隐", "ability_change": "能力变化", "career_changes": {{"main_career_stage_change": 0, "new_careers": []}}}}],
  "organization_states": [{{"organization": "组织名", "change": "变化描述", "power_change": 0}}],
  "key_plot_points": ["关键点"],
  "scenes": [{{"scene": "场景描述", "pacing": "fast/medium/slow", "tension": 5}}],
  "pacing": "medium",
  "dialogue_ratio": 0.35,
  "description_ratio": 0.4,
  "quality_scores": {{"pacing": 7, "engagement": 8, "coherence": 9, "writing_quality": 7, "character_depth": 8, "dialogue_quality": 7, "world_consistency": 9, "plot_logic": 8, "overall": 8}},
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
{chapter_content}""",
        "parameters": {"type": "object"},
    },
    {
        "name": "chapter_summary",
        "display_name": "章节摘要生成",
        "description": "为已写章节生成摘要",
        "category": "chapter",
        "skill_type": "builtin",
        "system_prompt": """请为以下章节生成简洁的摘要（200字以内），包含主要事件、人物行动和关键转折。

以 JSON 格式返回：{{"summary": "摘要内容", "key_events": ["事件1", "事件2"]}}

章节号：{chapter_number}
标题：{chapter_title}

章节内容：
{chapter_content}""",
        "parameters": {"type": "object"},
    },
    {
        "name": "inspire",
        "display_name": "灵感激发",
        "description": "根据模糊想法生成创意",
        "category": "outline",
        "skill_type": "builtin",
        "system_prompt": """你是一位创意无限的网文策划师。用户有一个模糊的创作想法，请帮他拓展成具体的创作方案。

请以 JSON 格式返回：
{
  "title_suggestions": ["书名建议1", "书名建议2", "书名建议3"],
  "genre": "推荐题材",
  "synopsis": "300字以内的故事梗概",
  "highlight": "核心卖点/爽点",
  "world_outline": "世界观简述",
  "main_characters": [{"name": "角色名", "role": "定位", "brief": "简介"}],
  "plot_hooks": ["3个核心剧情钩子"],
  "target_audience": "目标读者",
  "similar_works": ["类似作品"]
}""",
        "parameters": {"type": "object", "properties": {"idea": {"type": "string"}}},
    },
    # ===== 初始化用：组织/职业/关系/地点/物品生成（提示词模板可编辑）=====
    {
        "name": "world_core_generate",
        "display_name": "核心世界观生成",
        "description": "生成核心世界观（时间/地点/氛围/规则四要素）",
        "category": "world",
        "skill_type": "builtin",
        "system_prompt": """你是资深网文世界观架构师。为小说生成核心世界观。
所有内容必须使用中文。

题材要求（{genre}）：根据题材特点构建合理的世界观框架。

请生成 4 个维度的核心世界观，每个维度 200-400 字（详细、具体、有画面感）：
- world_time_period：时间背景（具体到年代/时期/时代特征）
- world_location：地理位置（具体地点/环境/布局/特色）
- world_atmosphere：氛围基调（整体氛围/文化/社会风气）
- world_rules：世界规则（社会法则/力量体系/特殊规则/潜规则）

只返回纯 JSON：{{"world_time_period":"","world_location":"","world_atmosphere":"","world_rules":""}}""",
        "parameters": {"type": "object", "properties": {"genre": {"type": "string"}, "title": {"type": "string"}, "synopsis": {"type": "string"}}},
    },
    {
        "name": "world_detail_generate",
        "display_name": "详细世界设定生成",
        "description": "生成详细世界设定条目（地理/历史/势力等）",
        "category": "world",
        "skill_type": "builtin",
        "system_prompt": """你是世界观设定师。基于核心世界观生成详细设定条目。
所有内容必须使用中文。

每个条目 200-400 字，内容具体、有细节、有画面感。
只返回纯JSON数组：[{{"name":"条目名","category":"分类","content":"200-400字详细描述"}}]
分类从以下选择：地理/历史/种族/势力/修炼体系/科技/文化/经济/军事/宗教/风俗/其他
生成 6-8 个条目。""",
        "parameters": {"type": "object", "properties": {"genre": {"type": "string"}, "title": {"type": "string"}, "world_info": {"type": "string"}}},
    },
    {
        "name": "organization_generate",
        "display_name": "组织势力生成",
        "description": "生成组织/势力",
        "category": "character",
        "skill_type": "builtin",
        "system_prompt": """你是网文势力设定师。为小说生成组织/势力。
所有内容必须使用中文。
只返回纯JSON数组，每个组织包含：name(名称)、org_type(类型)、description(描述200字)、power_value(势力值0-100)、location(所在地)、motto(格言)。
生成3-5个组织，类型多样（门派/商会/朝廷/帮派/家族等）。
{user_prompt}""",
        "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "genre": {"type": "string"}, "world_info": {"type": "string"}, "user_prompt": {"type": "string"}}},
    },
    {
        "name": "career_system_generation",
        "display_name": "职业体系生成",
        "description": "生成职业/修炼体系",
        "category": "character",
        "skill_type": "builtin",
        "system_prompt": """你是网文职业体系设计师。根据世界观生成职业体系。
所有内容必须使用中文。
只返回纯JSON数组：[{{"name":"职业名","career_type":"main或sub","category":"分类","description":"描述","stages":[{{"name":"阶段名","requirement":"要求"}}],"abilities":["能力"]}}]
生成3-5个职业，每个含进阶阶段。
{user_prompt}""",
        "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "genre": {"type": "string"}, "world_info": {"type": "string"}, "user_prompt": {"type": "string"}}},
    },
    {
        "name": "character_relations_generate",
        "display_name": "角色关系图谱生成",
        "description": "分析角色间关系并生成关系图谱",
        "category": "character",
        "skill_type": "builtin",
        "system_prompt": """你是角色关系分析师。根据角色列表，分析他们之间的关系。
只返回纯JSON数组：[{{"from":"角色A名","to":"角色B名","relation_type":"关系类型","category":"family/romantic/hostile/professional/social","intimacy":50,"description":"关系描述"}}]
intimacy 范围 -100 到 100。生成 5-8 条主要关系。""",
        "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "characters_info": {"type": "string"}}},
    },
    {
        "name": "locations_generate",
        "display_name": "地点地图生成",
        "description": "生成重要地点",
        "category": "world",
        "skill_type": "builtin",
        "system_prompt": """你是世界观设定师。为小说生成重要地点。
所有内容必须使用中文（包括地名、描述、氛围等）。
只返回纯JSON数组：[{{"name":"地点名（中文）","location_type":"城市/区域/建筑/秘境/自然景观","description":"100-200字中文描述","atmosphere":"氛围（中文）","importance":"normal/major/key"}}]
生成 5-8 个地点，至少 1 个重要地点。""",
        "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "world_info": {"type": "string"}}},
    },
    {
        "name": "items_generate",
        "display_name": "物品道具生成",
        "description": "生成重要物品/道具",
        "category": "world",
        "skill_type": "builtin",
        "system_prompt": """你是网文物品设定师。为小说生成重要物品/道具。
所有内容必须使用中文（包括物品名、描述等）。
只返回纯JSON数组：[{{"name":"物品名（中文）","category":"装备/消耗/关键道具/材料","rarity":"common/uncommon/rare/epic/legendary","item_type":"类型（中文）","description":"100-200字中文描述","is_key_item":0}}]
生成 5-8 个物品，至少 1 个关键剧情道具(is_key_item=1)。""",
        "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "world_info": {"type": "string"}}},
    },
    # ===== 卷摘要生成（方案 A：分层摘要链）=====
    {
        "name": "volume_summary",
        "display_name": "卷摘要生成",
        "description": "每 N 章自动生成一个卷级摘要，保障长期连贯性",
        "category": "analysis",
        "skill_type": "builtin",
        "system_prompt": """你是一位资深小说编辑。请根据以下连续章节的摘要和关键情节点，生成一段精炼的卷级摘要。

要求：
1. 摘要 200-400 字，概括本卷的核心剧情线
2. 必须包含：主线冲突演进、关键转折点、角色成长/变化、未解悬念
3. 用时间线叙事，不要逐章罗列，而是提炼出"这一卷讲了什么"
4. 结尾点明当前故事状态（进展到什么阶段、留下什么悬念）

【章节摘要】
{chapters_summary}

【关键情节点】
{key_plot_points}

请以纯 JSON 返回：
{{"volume_summary": "200-400字卷级摘要", "main_arc": "本卷主线一句话概括", "turning_points": ["转折1", "转折2"], "current_state": "当前故事状态一句话"}}""",
        "parameters": {"type": "object", "properties": {
            "chapters_summary": {"type": "string", "description": "本卷各章摘要"},
            "key_plot_points": {"type": "string", "description": "本卷关键情节点"},
        }},
    },
]


async def init_builtin_skills(db: AsyncSession):
    """初始化内置 Skill（仅首次启动种入 DB，已有同名 skill 不覆盖）。

    注意：DB 是唯一真相源。builtin 只是种子，启动后以 DB 为准。
    用户在「提示词模板」页编辑的提示词直接写 DB，生效优先级最高。
    落库代码有多别名兼容层，无论用哪套字段名都能正确映射到模型字段。
    """
    for skill_data in BUILTIN_SKILLS:
        result = await db.execute(select(Skill).where(Skill.name == skill_data["name"]))
        existing = result.scalar_one_or_none()
        if not existing:
            skill = Skill(**skill_data)
            db.add(skill)
    await db.commit()