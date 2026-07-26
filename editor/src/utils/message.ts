/**
 * 文件功能：提供全局轻量消息提示，并兼容导出统一确认弹窗接口。
 */
import { createApp, h, ref } from 'vue'
import { CheckCircle, AlertCircle, Info, XCircle } from '@lucide/vue'

export { createConfirm } from './confirm'

/**
 * 轻量级全局消息提示工具，替代 ElMessage。
 */

type MessageType = 'success' | 'error' | 'warning' | 'info'

interface MessageOptions {
  message: string
  type?: MessageType
  duration?: number
}

// 消息列队
const messages = ref<(MessageOptions & { id: number })[]>([])
let msgId = 0

/**
 * 消息组件定义
 */
const MessageContainer = {
  setup() {
    return () => h(
      'div',
{ class: 'fixed top-6 left-1/2 -translate-x-1/2 flex flex-col gap-3 z-toast pointer-events-none' },
      messages.value.map(msg => h(
        'div',
        {
          key: msg.id,
          class: [
            'flex items-center gap-3 px-4 py-3 rounded-xl shadow-lg border border-border min-w-[300px] pointer-events-auto transition-all transform duration-300 bg-surface animate-in slide-in-from-top-4 fade-in',
            msg.type === 'success' ? 'bg-success-muted border-success-border text-success-strong' : '',
            msg.type === 'error' ? 'bg-danger-muted border-danger-border text-danger-strong' : '',
            msg.type === 'warning' ? 'bg-warning-muted border-warning-border text-warning-strong' : '',
            msg.type === 'info' ? 'bg-info-muted border-info-border text-info-strong' : '',
          ]
        },
        [
          h(msg.type === 'success' ? CheckCircle : msg.type === 'error' ? XCircle : msg.type === 'warning' ? AlertCircle : Info, { class: 'w-5 h-5 flex-shrink-0' }),
          h('span', { class: 'text-sm font-semibold' }, msg.message)
        ]
      ))
    )
  }
}

// 挂载容器
let containerCreated = false
function ensureContainer() {
  if (containerCreated) return
  const div = document.createElement('div')
  div.id = 'base-message-container'
  document.body.appendChild(div)
  createApp(MessageContainer).mount(div)
  containerCreated = true
}

export const Message = {
  show(options: MessageOptions) {
    ensureContainer()
    const id = msgId++
    const msg = { ...options, id, type: options.type || 'info' }
    messages.value.push(msg)
    
    setTimeout(() => {
      const index = messages.value.findIndex(m => m.id === id)
      if (index > -1) messages.value.splice(index, 1)
    }, options.duration || 3000)
  },
  success(message: string) { this.show({ message, type: 'success' }) },
  error(message: string) { this.show({ message, type: 'error' }) },
  warning(message: string) { this.show({ message, type: 'warning' }) },
  info(message: string) { this.show({ message, type: 'info' }) },
}
