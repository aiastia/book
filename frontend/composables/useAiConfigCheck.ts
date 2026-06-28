/** 检查是否已配置 AI 模型。未配置时引导用户前往设置页。 */
export function useAiConfigCheck() {
  const msg = useMessage()
  const configured = ref<boolean | null>(null)

  async function check() {
    if (configured.value !== null) return configured.value
    try {
      const models = await useFetch?.('/api/ai-models', { timeout: 5000 }) || []
      configured.value = Array.isArray(models) && models.length > 0
    } catch {
      configured.value = false
    }
    return configured.value
  }

  return { configured, check }
}
