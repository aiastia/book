// 统一消息提示封装 —— 替代所有 alert() / confirm()
// 用法: const msg = useMessage() → msg.success('...') / msg.error('...') / await msg.confirm('...')
import { message, Modal } from 'ant-design-vue'

export function useMessage() {
  function success(text: string) {
    message.success(text)
  }

  function error(text: string) {
    message.error(text)
  }

  function warning(text: string) {
    message.warning(text)
  }

  function info(text: string) {
    message.info(text)
  }

  /** 加载中提示，返回关闭函数 */
  function loading(text: string, duration = 0) {
    return message.loading(text, duration)
  }

  async function confirm(text: string, title = '确认操作'): Promise<boolean> {
    return new Promise((resolve) => {
      Modal.confirm({
        title,
        content: text,
        okText: '确认',
        cancelText: '取消',
        onOk: () => resolve(true),
        onCancel: () => resolve(false),
      })
    })
  }

  return { success, error, warning, info, loading, confirm }
}
