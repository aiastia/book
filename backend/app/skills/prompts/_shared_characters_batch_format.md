<!--
模块：角色批量输出格式（仅 characters_batch_generation.md 使用）
职责：批量角色生成的 JSON 输出 schema，比单角色格式多了境界字段。

引用方式：
  characters_batch_generation.md → 本格式（输出 JSON 数组）
-->

只返回纯 JSON 数组（不要 markdown 代码块），每个角色包含：
[{
  "name": "角色名（中文，必须原创、避免模板化）",
  "role": "主角/配角/反派/路人",
  "gender": "性别",
  "age": "年龄",
  "identity": "社会身份（如：学生/剑客/皇子/商人。多位面题材冠以位面标签）",
  "main_career": "主职业（从已有职业体系中选择，必须填写）",
  "main_career_stage": "主职业当前境界",
  "sub_careers": ["副职业名列表（从已有职业体系中选择，如无则空数组）"],
  "sub_career_stages": ["副职业境界名列表"],
  "appearance": "外貌描述（100-200字）",
  "personality": "性格特征（包含优点和缺点，100-200字）",
  "background": "背景故事（100-300字。多位面题材包含跨世界设定）",
  "growth_experience": "成长经历（影响性格形成的关键事件，100-200字，必须填写）",
  "ability": "能力/技能（具体描述，必须填写，不能为空）",
  "story_goal": "故事目标（角色想要达成什么，必须填写）",
  "motivation": "内在动机（为什么追求这个目标，必须填写）",
  "weakness": "弱点/软肋（必须填写）",
  "arc_type": "变化类型（成长/堕落/救赎/顿悟/平淡）",
  "character_change": "人物变化轨迹（从什么变成什么）",
  "speech_style": "说话风格特征（如：冷静寡言/活泼话多/文绉绉/粗犷直白）",
  "organization_memberships": ["角色所属的组织名（从已有组织中选择，无组织则返回空数组 []）"]
}]
