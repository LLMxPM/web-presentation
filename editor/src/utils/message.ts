import { createApp, h, ref } from 'vue'
import { CheckCircle, AlertCircle, Info, XCircle } from 'lucide-vue-next'

/**
 * 轻量级全局消息提示与弹窗工具，替代 ElMessage 和 ElMessageBox
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
      { class: 'fixed top-6 left-1/2 -translate-x-1/2 flex flex-col gap-3 z-[2000] pointer-events-none' },
      messages.value.map(msg => h(
        'div',
        {
          key: msg.id,
          class: [
            'flex items-center gap-3 px-4 py-3 rounded-xl shadow-lg border border-slate-200 min-w-[300px] pointer-events-auto transition-all transform duration-300 bg-white animate-in slide-in-from-top-4 fade-in',
            msg.type === 'success' ? 'bg-emerald-50 border-emerald-100 text-emerald-700' : '',
            msg.type === 'error' ? 'bg-red-50 border-red-100 text-red-700' : '',
            msg.type === 'warning' ? 'bg-orange-50 border-orange-100 text-orange-700' : '',
            msg.type === 'info' ? 'bg-blue-50 border-blue-100 text-blue-700' : '',
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

// ----------------- Confirm 弹窗 -----------------

export function createConfirm(message: string, title = '操作确认') {
  return new Promise((resolve) => {
    const div = document.createElement('div')
    document.body.appendChild(div)
    
    const app = createApp({
      setup() {
        const visible = ref(true)
        const handleCancel = () => {
          visible.value = false
          setTimeout(() => {
            app.unmount()
            div.remove()
            resolve(false)
          }, 300)
        }
        const handleConfirm = () => {
          visible.value = false
          setTimeout(() => {
            app.unmount()
            div.remove()
            resolve(true)
          }, 300)
        }
        
        return () => h('div', { class: ['fixed inset-0 z-[1100] flex items-center justify-center p-4 transition-opacity duration-300', visible.value ? 'opacity-100' : 'opacity-0'] }, [
          h('div', { class: 'absolute inset-0 bg-slate-900/40 backdrop-blur-sm', onClick: handleCancel }),
          h('div', { class: ['relative w-full max-w-[400px] bg-white rounded-2xl shadow-xl overflow-hidden transform transition-all duration-300', visible.value ? 'scale-100' : 'scale-90 opacity-0'] }, [
            h('div', { class: 'px-6 py-5' }, [
              h('h3', { class: 'text-lg font-bold text-slate-900 mb-2' }, title),
              h('p', { class: 'text-slate-600 text-sm leading-relaxed' }, message)
            ]),
            h('div', { class: 'px-6 py-4 bg-slate-50 flex justify-end gap-3' }, [
              h('button', { class: 'px-4 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-200 rounded-lg transition-colors', onClick: handleCancel }, '取消'),
              h('button', { class: 'px-4 py-2 text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg transition-colors shadow-sm', onClick: handleConfirm }, '确定')
            ])
          ])
        ])
      }
    })
    
    app.mount(div)
  })
}
