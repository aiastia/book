# 提示词变量参考

## 章节生成（4 个提示词共用）

| 变量 | 来源 | 说明 |
|------|------|------|
| `{project_title}` | `project.title` | 小说名称 |
| `{chapter_number}` | `chapter.chapter_number` | 当前章节号 |
| `{chapter_title}` | `chapter.title` | 章节标题 |
| `{target_word_count}` | 用户指定 | 目标字数 |
| `{narrative_perspective}` | `project.narrative_pov` | 叙事视角（第一/三人称） |
| `{genre}` | `project.genre` | 小说类型 |
| `{chapter_outline}` | `expansion_plan` 或 `outline` | 本章大纲/规划 |
| `{characters_info}` | `_get_important_context` | 角色完整信息 |
| `{chapter_careers}` | `_get_important_context` | 本章职业信息 |
| `{foreshadow_reminders}` | `_get_reference_context` | 伏笔提醒 |
| `{relevant_memories}` | `_get_vector_memory_context` | 向量召回的相关记忆 |
| `{chapter_data}` | `_preload_chapter_data` | 轻量预加载数据（tool-calling模式） |
| `{user_prompt}` | 固定文本 | AI 创作指令 |

## 1→N 续章专属

| 变量 | 说明 |
|------|------|
| `{continuation_point}` | 上一章末尾衔接点（500字） |
| `{previous_chapter_summary}` | 上一章摘要 |
| `{recent_chapters_context}` | 最近几章上下文 |
| `{quality_trends}` | 评分趋势反馈 |

## 共享模块

| 变量 | 文件 | 说明 |
|------|------|------|
| `{scene_anchor}` | `_shared_chapter_context.md` | 本章核心空间感官锚点 |
| `{character_intents}` | `_shared_chapter_context.md` | 角色微意图列表 |

## 大纲展开

| 变量 | 文件 | 说明 |
|------|------|------|
| `{outline_order_index}` | `outline_expand_single.md` | 大纲序号 |
| `{outline_title}` | `outline_expand_single.md` | 大纲标题 |
| `{outline_content}` | `outline_expand_single.md` | 大纲内容 |
| `{target_chapter_count}` | `outline_expand_single.md` | 目标展开章节数 |
| `{strategy_instruction}` | `outline_expand_single.md` | 展开策略（balanced/climax/detail） |
| `{project_genre}` | `outline_expand_single.md` | 小说类型 |
| `{project_theme}` | `outline_expand_single.md` | 小说主题 |
| `{project_narrative_perspective}` | `outline_expand_single.md` | 叙事视角 |
| `{project_world_time_period}` | `outline_expand_single.md` | 世界观时间背景 |
| `{project_world_location}` | `outline_expand_single.md` | 世界观地理位置 |
| `{project_world_atmosphere}` | `outline_expand_single.md` | 世界观氛围 |
| `{context_info}` | `outline_expand_single.md` | 上下文参考信息 |
| `{synopsis}` | `outline_expand_single.md` | 小说简介 |

## 自动组织分析/生成

| 变量 | 说明 |
|------|------|
| `{title}`, `{genre}`, `{theme}` | 项目基本信息 |
| `{time_period}`, `{location}`, `{atmosphere}` | 世界观维度 |
| `{existing_characters}`, `{existing_organizations}` | 已有角色/组织 |
| `{all_chapters_brief}`, `{chapter_count}` | 全部章节摘要和数量 |
| `{plot_stage}`, `{story_direction}` | 情节阶段和方向 |
| `{start_chapter}`, `{end_chapter}` | 起止章节 |
| `{organization_specification}`, `{rules}`, `{plot_context}` | 组织规格/规则/情节上下文 |

## 章节分析

| 变量 | 文件 | 说明 |
|------|------|------|
| `{chapter_content}` | `plot_analysis.md` | 章节正文 |
| `{existing_foreshadows}` | `plot_analysis.md` | 已有伏笔列表 |
| `{word_count}` | `plot_analysis.md` | 实际字数 |

## 部分改写

| 变量 | 说明 |
|------|------|
| `{selected_text}` | 选中文本 |
| `{context_before}` / `{context_after}` | 上下文 |
| `{original_word_count}` | 原文字数 |
| `{length_requirement}` | 长度要求 |
| `{style_content}` | 风格参考 |
| `{user_instructions}` | 用户指令 |

## 书导入

| 变量 | 说明 |
|------|------|
| `{chapters_text}` | 章节文本 |
| `{sampled_text}` | 采样文本 |
| `{expected_count}` | 预期大纲数 |

## 灵感

| 变量 | 说明 |
|------|------|
| `{initial_idea}` | 初始想法 |
| `{existing}` | 已有内容 |
| `{description}` | 书名/描述 |

## 全局

| 变量 | 说明 |
|------|------|
| `{user_input}`, `{user_instructions}` | 用户输入 |
| `{project_context}` | 项目上下文 |
| `{word_count}`, `{chapter_count}` | 字数/章数 |
