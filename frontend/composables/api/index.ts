/** 墨鱼写作系统 · 统一 API
 *
 * 用法：
 *   import { API } from '~/composables/api'
 *   await API.book.list()
 *   await API.chapter.batchGenerate(17, { start: 3, count: 5 })
 */
import { bookApi } from './book.api'
import { chapterApi } from './chapter.api'
import { outlineApi } from './outline.api'
import { characterApi } from './character.api'
import { itemApi } from './item.api'
import { locationApi } from './location.api'
import { worldApi } from './world.api'
import { organizationApi } from './organization.api'
import { foreshadowApi } from './foreshadow.api'
import { relationApi } from './relation.api'
import { aiApi } from './ai.api'
import { taskApi } from './task.api'
import { memoryApi } from './memory.api'
import { promptApi } from './prompt.api'
import { globalApi } from './global.api'
import { bookImportApi } from './book-import.api'
import { skillApi } from './skill.api'
import { careerApi } from './career.api'
import { charCareerApi } from './char-career.api'

export const API = {
  book: bookApi,
  chapter: chapterApi,
  outline: outlineApi,
  character: characterApi,
  item: itemApi,
  location: locationApi,
  world: worldApi,
  organization: organizationApi,
  foreshadow: foreshadowApi,
  relation: relationApi,
  ai: aiApi,
  task: taskApi,
  memory: memoryApi,
  prompt: promptApi,
  global: globalApi,
  bookImport: bookImportApi,
  skill: skillApi,
  career: careerApi,
  charCareer: charCareerApi,
}

export { pid } from './client'
