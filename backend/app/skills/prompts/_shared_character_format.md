<!--
模块：角色输出格式（仅 character_generate.md 使用）
职责：单角色生成的 JSON 输出 schema。

引用方式：
  character_generate.md → 本格式（输出一个 JSON 对象）
-->

请以 JSON 格式返回：
{
  "name": "角色名（中文）",
  "role": "主角/配角/反派/路人",
  "gender": "性别",
  "age": "年龄",
  "identity": "社会身份（如：学生/剑客/皇子/商人。多位面题材冠以位面标签）",
  "main_career": "主职业（从已有职业体系中选择，如无则留空）",
  "sub_careers": ["副职业列表（从已有职业体系中选择，如无则空数组）"],
  "appearance": "外貌描述（100-200字）",
  "personality": "性格特征（包含优点和缺点，100-200字）",
  "background": "背景故事（100-300字。多位面题材包含跨世界设定）",
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
}
