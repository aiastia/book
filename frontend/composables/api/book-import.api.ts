import { get, post, del } from './client'
export const bookImportApi = {
  upload: (body: any) => post('/book-import/upload', body),
  delete: (bookId: number) => del(`/book-import/${bookId}`),
  get: (bookId: number) => get(`/book-import/${bookId}`),
  deconstruct: (bookId: number, body: any) => post(`/book-import/${bookId}/deconstruct`, body),
  parseTxt: (body: any) => post('/projects/book-import/parse-txt', body),
  fullImport: (body: any) => post('/projects/book-import/full-import', body),
  suggest: (body: any) => post('/book-import/reverse-suggest', body),
  reverseOutlines: (body: any) => post('/book-import/reverse-outlines', body),
}
