/** AI 模型 API */
import { get, post, put, del, pid } from './client'
const P = (id?: number) => id || pid()
export const aiApi = {
  listModels: () => get('/ai-models'),
  createModel: (body: any) => post('/ai-models', body),
  updateModel: (modelId: number, body: any) => put(`/ai-models/${modelId}`, body),
  deleteModel: (modelId: number) => del(`/ai-models/${modelId}`),
  testModel: (modelId: number) => post(`/ai-models/${modelId}/test`),
  fetchDefaultRemoteModels: () => get('/ai-models/default/remote-models'),
  testRewrite: (baseUrl: string, apiKey: string, model: string) =>
    post('/ai-models/test-rewrite', { base_url: baseUrl, api_key: apiKey, model }),
  testEmbedding: (baseUrl: string, apiKey: string, embeddingModel: string) =>
    post('/ai-models/test-embedding', { base_url: baseUrl, api_key: apiKey, embedding_model: embeddingModel }),
  fetchRemoteModels: (baseUrl: string, apiKey: string, provider = 'openai') =>
    post('/ai-models/fetch-remote', { base_url: baseUrl, api_key: apiKey, provider }),
  fetchModelRemoteModels: (modelId: number) => get(`/ai-models/${modelId}/remote-models`),
  fetchRewriteRemoteModels: (baseUrl: string, apiKey: string, provider = 'openai') =>
    post('/ai-models/fetch-remote', { base_url: baseUrl, api_key: apiKey, provider }),
  // 封面
  generateCoverPrompt: (id?: number) => post(`/projects/${P(id)}/cover/generate-prompt`),
  generateCoverImage: (prompt: string, id?: number) => post(`/projects/${P(id)}/cover/generate-image`, { prompt }),
}
