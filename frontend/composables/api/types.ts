/** 墨鱼写作系统 · 共享类型 */

// ==================== 项目 ====================
export interface Project {
  id: number; title: string; genre: string; synopsis: string
  outline_mode: string; narrative_pov: string
  target_word_count?: number; current_word_count?: number
  chapter_count?: number; status?: string; cover_url?: string
  writing_style?: { name?: string; style_id?: number; config?: any }
  settings?: Record<string, any>
  world_time_period?: string; world_location?: string
  world_atmosphere?: string; world_rules?: string
}

export interface BookSummary {
  id: number; title: string; genre?: string; synopsis?: string
  outline_mode?: string; chapter_count?: number
  word_count?: number; current_word_count?: number
  status?: string; cover_url?: string; target_word_count?: number
  narrative_pov?: string
}

// ==================== 章节 ====================
export interface Chapter {
  id: number; chapter_number: number; title: string
  word_count: number; status: string; summary?: string
  content_preview?: string; content?: string
  outline_id?: number; sub_index?: number
  generation_mode?: string; has_expansion_plan?: boolean
  analyzed?: boolean; quality_score?: number
  expansion_plan?: Record<string, any>
  raw_output?: string; generation_history?: any[]; quality_alert?: any
}

// ==================== 大纲 ====================
export interface Outline {
  id: number; chapter_number: number; title: string
  summary?: string; emotion?: string; goal?: string
  characters?: string[]; organizations?: string[]
  key_points?: string[]; scenes?: any[]
  structure?: Record<string, any>; expansion_plan?: Record<string, any>
  chapter_count?: number; has_chapters?: boolean
}

// ==================== 角色 ====================
export interface Character {
  id: number; name: string; role?: string; gender?: string
  age?: string; identity?: string; personality?: string
  appearance?: string; background?: string; status?: string
  main_career_id?: number; main_career_stage?: number; main_career_stage_desc?: string
  sub_careers?: string; avatar_url?: string; tags?: string[]
  organization_id?: number
}

// ==================== 组织 ====================
export interface Organization {
  id: number; name: string; org_type?: string
  description?: string; power_level?: number; location?: string
  motto?: string; color?: string; member_count?: number
  personality?: string; purpose?: string; traits?: string[]
}

export interface OrgMember {
  id: number; organization_id: number; character_id: number
  position?: string; rank?: number; status?: string
  loyalty?: number; contribution?: number
}

// ==================== 物品 / 地点 ====================
export interface Item {
  id: number; name: string; category?: string; rarity?: string
  item_type?: string; description?: string; owner_name?: string
  status?: string; obtained_chapter?: number
  is_key_item?: boolean; quantity?: number; attributes?: any
}

export interface Location {
  id: number; name: string; location_type?: string
  description?: string; atmosphere?: string; danger_level?: string
  parent_location?: string
}

// ==================== 世界观 ====================
export interface WorldSetting {
  id: number; name: string; category?: string; content?: string
}

export interface WorldCore {
  world_time_period?: string; world_location?: string
  world_atmosphere?: string; world_rules?: string
}

// ==================== 伏笔 ====================
export interface Foreshadow {
  id: number; title: string; content?: string
  status: string; foreshadow_type?: string
  plant_chapter?: number; target_chapter?: number
}

// ==================== 任务 ====================
export interface BackgroundTask {
  id: number; task_type: string; title: string
  status: string; progress: number; status_message?: string
  stage?: string; progress_details?: Record<string, any>
  completed_chapters?: number; total_chapters?: number
  failed_chapters?: any[]; error?: string
}

// ==================== 关系 ====================
export interface RelationType {
  id?: number; name: string; label?: string
  category?: string; count?: number
}

export interface Relation {
  id: number; from_name?: string; to_name?: string
  relation_type?: string; intimacy?: number; status?: string
  description?: string
}

// ==================== AI 模型 ====================
export interface AIModelConfig {
  id: number; name: string; model: string
  is_default: boolean; provider?: string; base_url?: string
  api_key?: string; temperature?: number; top_p?: number; max_tokens?: number
  frequency_penalty?: number; presence_penalty?: number
  reasoning_model?: boolean; reasoning_effort?: string
  rewrite_model?: string; rewrite_base_url?: string; rewrite_api_key?: string
  image_model?: string; image_base_url?: string; image_api_key?: string
  backend_type?: string
  embedding_model?: string
}

// ==================== 写作风格 ====================
export interface WritingStyle {
  id: number; name: string; is_default?: boolean
  style_type?: string
}

// ==================== 记忆 ====================
export interface StoryMemory {
  id: number; memory_type?: string; title?: string
  content?: string; importance?: number; chapter_number?: number
}

// ==================== 剧情分析 ====================
export interface PlotAnalysis {
  id: number; chapter_number: number; chapter_title?: string
  plot_stage?: string; conflict_level?: number; pacing?: string
  overall_quality_score?: number; quality_scores?: any
}

// ==================== 职业 ====================
export interface Career {
  id: number; name: string; career_type?: string
  category?: string; description?: string
  stages?: any[]; max_stage?: number; abilities?: any[]; attributes?: any
}

export interface CharacterCareer {
  id: number; character_id: number; character_name?: string
  career_id: number; career_name?: string
  career_type?: string; current_stage?: number
}

// ==================== 待补充实体 ====================
export interface PendingEntities {
  pending_items: { name: string; category: string; description: string; from_chapter: number }[]
  pending_locations: { name: string; location_type: string; description: string; from_chapter: number }[]
  total: number
}

// ==================== 全局 ====================
export interface GlobalStats {
  projects?: number; chapters?: number; words?: number
  characters?: number
}
