// 统一错误信息格式化 —— 解决 [object Object] 问题
// 用法：msg.error('创建失败：' + formatError(e))
// 或：  msg.error(formatError(e, '创建失败'))
//
// 背景：Nuxt $fetch 抛出的错误结构是 e.data = {detail: ...}
// 后端 FastAPI 的 HTTPException(detail=...) 会把 detail 放在 e.data.detail
// - 当 detail 是字符串：直接显示
// - 当 detail 是对象/数组（如 Pydantic 422 校验错误）：直接用 + 拼接会变成 [object Object]
// 本函数统一处理这两种情况。

export function formatError(e: any, fallback = '操作失败'): string {
  // 优先取 FastAPI 的 detail
  const detail = e?.data?.detail ?? e?.data?.message ?? e?.message ?? e?.statusMessage
  if (typeof detail === 'string' && detail.trim()) return detail
  // detail 是对象/数组：尝试取常见字段，否则 JSON 序列化
  if (detail && typeof detail === 'object') {
    // Pydantic 校验错误是数组 [{msg, ...}]，取 msg 拼接更友好
    if (Array.isArray(detail)) {
      const msgs = detail
        .map((d: any) => (typeof d === 'string' ? d : d?.msg || d?.message || ''))
        .filter(Boolean)
      if (msgs.length) return msgs.join('；')
    }
    return JSON.stringify(detail)
  }
  return fallback
}
