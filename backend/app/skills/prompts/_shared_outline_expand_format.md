<!--
模块：大纲展开格式（仅 outline_expand_single.md 使用）
职责：定义展开模式下的字段别名、扩展字段和格式约束，与基础格式模板配合使用。

引用方式：
  outline_expand_single.md → 本格式（与 _shared_outline_format.md 共同构成展开模式的完整输出 schema）
-->

【字段映射】
以下为展开模式下的字段别名，输出时使用共享格式的标准字段名：
  sub_index        → chapter_number（子章节序号，从1开始）
  plot_summary     → summary（200-300字剧情摘要，前三分之一必须是人物正在做的动作或刚接收到的新信息，不允许做环境铺陈）
  key_events       → key_points（【重点】关键事件列表）
  character_focus  → characters（本章聚焦角色名数组）
  emotional_arc    → emotion（情绪变化，格式：起点情绪→触发事件→转折情绪→结尾残留情绪）
  narrative_goal   → goal（叙事目标，必须是具体的读者感受，不是抽象概括）

【扩展字段】
  "conflict_type": "冲突类型（如：内心挣扎、人际冲突、信息不对等对抗）",
  "hook": "本章结尾钩子（必须是一个具体的中断：写到哪个动作即将完成时停住、哪句话说到一半时打断、哪个信息正要确认时切断。禁止写总结句）",
  "rhythm_tag": "起/承/小高潮（该大纲节点拆分的最后一章必须填'小高潮'）"

【爽点设计格式】
shuang_design 字段在展开模式下使用对象格式：
{
  "info_asymmetry": "本章存在的信息不对称",
  "shock_level": "点震惊/网震惊/深度震惊/无",
  "spectator_layers": ["路人反应", "同行/内行反应", "权威/高层反应", "反派阵营反应"],
  "emotional_rhythm": "情绪拉扯描述",
  "protagonist_style": "主角逼格展示方式（具体行为场景描述）"
}

【格式约束】
- 纯JSON数组输出，无其他文字
- 内容描述中严禁使用特殊符号
