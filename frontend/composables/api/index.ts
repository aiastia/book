/** 墨鱼写作系统 · 统一 API
 *
 * 用法：
 *   import { API } from '~/composables/api'
 *   await API.book.list()
 *   await API.chapter.batchGenerate(17, { start: 3, count: 5 })
 *   const outlines = await API.outline.list()
 */
export { bookApi as book } from './book.api'
export { chapterApi as chapter } from './chapter.api'
export { outlineApi as outline } from './outline.api'
export { characterApi as character } from './character.api'
export { itemApi as item } from './item.api'
export { locationApi as location } from './location.api'
export { worldApi as world } from './world.api'
export { organizationApi as organization } from './organization.api'
export { foreshadowApi as foreshadow } from './foreshadow.api'
export { relationApi as relation } from './relation.api'
export { aiApi as ai } from './ai.api'
export { taskApi as task } from './task.api'
export { memoryApi as memory } from './memory.api'
export { pid } from './client'
export { promptApi as prompt } from './prompt.api'
export { globalApi as global } from './global.api'
export { bookImportApi as bookImport } from './book-import.api'
export { skillApi as skill } from './skill.api'
export { careerApi as career } from './career.api'
