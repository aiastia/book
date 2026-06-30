<!--
模块：大纲输出格式（所有大纲提示词共用）
职责：统一章节大纲的 JSON 输出 schema，消除各提示词间的格式差异。

引用方式：
  outline_create.md                → 本格式
  outline_continue.md              → 本格式
  book_import_reverse_outlines.md  → 本格式
  outline_expand_single.md         → 本格式 + _shared_outline_expand_format.md（展开独有字段另见后者）
-->

请以 JSON 数组格式返回，数组长度严格等于要求生成的章数：

[
  {
    "chapter_number": N,
    "title": "章节标题",
    "summary": "200字以内的章节概要，必须包含本章的「脉冲点」（即让读者感到爽/燃/甜/虐的关键时刻，如扮猪吃虎的揭晓瞬间、信息差碾压的高光、感情升温的名场面、伏笔回收的恍然等）",
    "scenes": [{"scene_title": "地点/环境名", "scene_desc": " 纯环境描写（必填）：在哪里、什么样子、什么氛围（光线/声音/气味/温度/质感）。禁止写角色动作、对话、事件", "emotion": "情绪基调"}],
    "characters": ["正式角色名（从已有角色列表选或创建新的人物名字，禁止泛称和组织名）"],
    "organizations": ["组织名（从已有组织列表选或创建新的组织名字，没有则留空）"],
    "key_points": ["关键情节点（带优先级+字数分配，如【重点·600字】xxx / 【一般·300字】xxx / 【弱·100字】xxx）"],
    "chapter_advance": "本章推进目标：本章结束时状态发生了什么变化（必填，不能原地踏步。如：主角从'被动等待'变为'主动掌握筹码'）",
    "emotion": "情绪弧线（如：专注计算→结晶异变时的错愕→被追击的紧绷→被按住手腕的凝滞，3-4个带情境的节点）",
    "goal": "本章叙事目标",
    "shuang_design": "（可选）爽点设计",
    "reader_hook": "（可选）读者钩子",
    "decision_basis": "（可选）决策依据",
    "obstacle_type": "（可选）障碍类型",
    "hook_type": "（可选）钩子类型",
    "chapter_breath": "（可选）节奏",
    "foreshadow_plant": "（可选）伏笔埋设",
    "scene_anchor": "（推荐）场景锚点，50-80字感官细节。示例：「承乾宫寝殿——烛火只剩三盏，铜鹤嘴里吐出的不是香烟是冷气，床帐的流苏有一半被扯断了，地上有拖拽的痕迹」",
    "character_intents": [{"character": "角色名", "this_chapter_goal": "本章目标", "immediate_want": "此刻最想要的"}],
    "new_items": [{"name": "新物品名", "category": "装备/消耗品/材料/关键道具/杂物", "description": "一句话描述"}],
    "new_locations": [{"name": "新地点名", "location_type": "建筑/自然景观/秘境/城市/室内", "description": "一句话描述"}],
    "estimated_words": 3000
  }
]
