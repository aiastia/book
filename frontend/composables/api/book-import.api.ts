import { get, post, del } from './client'
export const bookImportApi = {
  upload: (body: any) => post('/projects/book-import/upload', body),
  delete: (bookId: number) => del(`/projects/book-import/${bookId}`),
  get: (bookId: number) => get(`/projects/book-import/${bookId}`),
  deconstruct: (bookId: number, body: any) => post(`/projects/book-import/${bookId}/deconstruct`, body),
  parseTxt: (body: any) => post('/projects/book-import/parse-txt', body),
  fullImport: (body: any) => post('/projects/book-import/full-import', body),
  suggest: (body: any) => post('/projects/book-import/reverse-suggest', body),
  reverseOutlines: (body: any) => post('/projects/book-import/reverse-outlines', body),
}
