// 统一消息提示封装 —— 替代所有 alert() / confirm()
// 用法: const msg = useMessage() → msg.success('...') / msg.error('...') / await msg.confirm('...')
import { message, Modal } from 'ant-design-vue'

export function useMessage() {
  function success(msg: string) {
    message.success(msg)
  }

  function error(msg: string) {
    message.error(msg)
  }

  function warning(msg: string) {
    message.warning(msg)
  }

  function info(msg: string) {
    message.info(msg)
  }

  async function confirm(msg: string, title = '确认操作'): Promise<boolean> {
    return new Promise((resolve) => {
      Modal.confirm({
        title,
        content: msg,
        okText: '确认',
        cancelText: '取消',
        onOk: () => resolve(true),
        onCancel: () => resolve(false),
      })
    })
  }

  return { success, error, warning, info, confirm }
}
