<!--
模块：大纲输出格式（outline_create + outline_continue 共用）
职责：统一 1→1 大纲模式的 JSON 输出 schema。

引用方式：
  outline_create.md   → 本格式（首次创建大纲）
  outline_continue.md → 本格式（续写大纲，额外含 decision_basis / obstacle_type / hook_type / chapter_breath）
-->

请以 JSON 数组格式返回：

[
  {
    "chapter_number": N,
    "title": "章节标题",
    "summary": "200字概要（含脉冲点/爽点）",
    "scenes": [{"scene_title": "场景名", "scene_desc": " 纯环境描写（必填，无角色动作）", "emotion": "情绪基调"}],
    "characters": ["正式角色名（从已有角色列表选或创建新的名字，禁止泛称和组织名）"],
    "organizations": ["组织名（从已有组织列表选或创建新的组织，没有则留空）"],
    "key_points": ["关键情节点（带优先级+字数分配）"],
    "chapter_advance": "本章推进目标：本章结束时状态发生了什么变化（必填，不能原地踏步）",
    "emotion": "情绪弧线（如：专注计算→结晶异变时的错愕→被追击的紧绷→被按住手腕的凝滞，3-4个带情境的节点）",
    "goal": "本章叙事目标",
    "shuang_design": "（可选）爽点设计",
    "reader_hook": "（可选）读者钩子",
    "foreshadow_plant": "（可选）伏笔埋设",
    "scene_anchor": "（推荐）场景锚点，50-80字感官细节",
    "character_intents": [{"character": "角色名", "this_chapter_goal": "本章目标", "immediate_want": "此刻最想要的"}],
    "new_items": [{"name": "新物品名", "category": "装备/消耗品/材料/关键道具/杂物", "description": "一句话描述"}],
    "new_locations": [{"name": "新地点名", "location_type": "建筑/自然景观/秘境/城市/室内", "description": "一句话描述"}]
  }
]

如果本章引入了新的物品或地点（已有列表中不存在的），在对应章节的 new_items / new_locations 中列出。同一物品/地点只在首次出现的章节声明，后续章节不需要重复。
