/** 文件功能：验证智能体运行详情弹窗使用 UiDialog 后仍保留关键交互与可访问行为。 */
import { defineComponent, nextTick, ref } from 'vue'
import { fireEvent, render, screen } from '@testing-library/vue'
import { afterEach, describe, expect, it } from 'vitest'

import AgentConversationDialogs from './AgentConversationDialogs.vue'
import type { ToolCallDetail } from './agent-conversation-panel'

afterEach(() => {
  document.body.innerHTML = ''
})

describe('AgentConversationDialogs', () => {
  it('工具详情弹窗应支持 Esc 关闭并恢复打开前的焦点', async () => {
    renderDialogHarness()

    const trigger = screen.getByRole('button', { name: '打开工具详情' })
    trigger.focus()
    await fireEvent.click(trigger)
    await nextTick()

    expect(screen.getByRole('button', { name: '关闭工具调用 · 保存页面' })).toHaveFocus()

    await fireEvent.keyDown(window, { key: 'Escape' })
    await nextTick()
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(screen.queryByText('工具输入')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

})

/** 构建受控弹窗宿主，覆盖 UiDialog 的打开、关闭和焦点恢复路径。 */
function renderDialogHarness() {
  const Harness = defineComponent({
    components: { AgentConversationDialogs },
    template: `
      <button type="button" @click="toolDetailVisible = true">打开工具详情</button>
      <AgentConversationDialogs
        :tool-detail-visible="toolDetailVisible"
        :active-tool-detail="toolDetail"
        @update:tool-detail-visible="toolDetailVisible = $event"
      />
    `,
    setup() {
      return {
        toolDetailVisible: ref(false),
        toolDetail: createToolDetail(),
      }
    },
  })

  return render(Harness)
}

/** 构造工具详情夹具，确保弹窗标题与复制区都具备稳定输入。 */
function createToolDetail(): ToolCallDetail {
  return {
    id: 'tool-item-1',
    runId: 'parent-run-1',
    toolCallId: 'tool-call-1',
    toolName: '保存页面',
    status: 'completed',
    inputPayload: { title: '演示页' },
    outputPayload: { pageId: 1 },
    message: '',
    progress: null,
    source: 'event',
    createdAt: '2026-07-24T10:00:00+08:00',
    attachments: [],
    inputAttachments: [],
    outputAttachments: [],
  }
}
