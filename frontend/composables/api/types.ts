/** 墨鱼写作系统 · 共享类型 */

// ==================== 项目 ====================
export interface Project {
  id: number; title: string; genre: string; synopsis: string
  outline_mode: 'one_to_one' | 'one_to_many'
  narrative_pov: string; target_word_count: number; current_word_count: number
  status: string; cover_url: string
  writing_style?: { name: string; style_id: number; config?: any }
  settings?: Record<string, any>
}

// ==================== 章节 ====================
export interface Chapter {
  id: number; chapter_number: number; title: string
  word_count: number; status: string; summary: string
  content_preview?: string; content?: string
  outline_id?: number; sub_index: number
  generation_mode?: string; has_expansion_plan: boolean
  analyzed: boolean; quality_score?: number
  expansion_plan?: Record<string, any>
  characters?: any[]
}

// ==================== 大纲 ====================
export interface Outline {
  id: number; chapter_number: number; title: string
  summary: string; emotion?: string; goal?: string
  characters: string[]; organizations: string[]
  key_points: string[]; scenes: any[]
  structure?: Record<string, any>
  expansion_plan?: Record<string, any>
}

// ==================== 角色 ====================
export interface Character {
  id: number; name: string; role: string; gender: string
  age?: string; identity?: string; personality?: string
  appearance?: string; background?: string
  main_career_id?: number; main_career_stage?: number
  organization_id?: number
}

// ==================== 任务 ====================
export interface BackgroundTask {
  id: number; task_type: string; title: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  progress: number; status_message: string; stage: string
  progress_details?: Record<string, any>
  completed_chapters?: number; total_chapters?: number
  failed_chapters?: any[]
}
