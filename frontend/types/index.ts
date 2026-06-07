// 后端数据类型定义（与 Python 后端约定的接口契约）
// Python 半成品后端实现这些接口后，前端即可拿到真实数据

export interface Book {
  id: number
  title: string
  cover?: string
  desc: string
  chapters: number
  words: string
  updated: string
  tag: string
  type: 'success' | 'warning' | 'info' | 'primary' | 'danger'
}

export interface Chapter {
  no: number
  title: string
  words: number
  updated: string
  status: string
  type: 'success' | 'warning' | 'info' | 'primary' | 'danger'
}

export interface OutlineItem {
  no: number
  title: string
  summary: string
  status: string
  type: 'success' | 'warning' | 'info' | 'primary' | 'danger'
}

export interface Character {
  name: string
  initial: string
  role: string
  desc: string
  tags: string[]
}

export interface LogEntry {
  date: string
  event: string
  type: 'success' | 'warning' | 'info' | 'primary' | 'danger'
}

export interface AiModel {
  name: string
  provider: string
  endpoint: string
  enabled: boolean
}

export interface Prompt {
  title: string
  category: string
  preview: string
  usage: number
}

export interface Skill {
  name: string
  desc: string
  enabled: boolean
  usage: number
}

export interface McpServer {
  name: string
  desc: string
  tools: number
  status: string
  type: 'success' | 'warning' | 'danger'
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface WorldSection {
  title: string
  items: string[]
}