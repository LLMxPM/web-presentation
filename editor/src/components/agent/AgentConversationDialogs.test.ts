/** 文件功能：验证智能体运行详情弹窗使用 UiDialog 后仍保留关键交互与可访问行为。 */
import { defineComponent, h, nextTick, ref } from 'vue'
import { fireEvent, render, screen } from '@testing-library/vue'
import { afterEach, describe, expect, it } from 'vitest'

import AgentConversationDialogs from './AgentConversationDialogs.vue'
import type { ToolCallDetail } from './agent-conversation-panel'
import type { AgentMemberRunItem } from '@/types/api'

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

  it('成员运行详情应保留默认层级、dense 内容区和运行切换', async () => {
    renderDialogHarness({ memberRunVisible: true })

    const shells = document.body.querySelectorAll('.dialog-shell')
    expect(shells).toHaveLength(1)
    expect(shells[0]).toHaveStyle({ zIndex: '1000' })
    expect(shells[0]).toHaveAttribute('data-dialog-body-preset', 'dense')

    await fireEvent.click(screen.getByRole('button', { name: '成员二' }))
    expect(screen.getByText('Run ID：member-run-2')).toBeInTheDocument()

    await fireEvent.click(screen.getByRole('button', { name: '展开成员消息' }))
    expect(screen.getByText('传入消息')).toBeInTheDocument()
    expect(screen.getByText('第二个成员输入')).toBeInTheDocument()
  })
})

/** 构建受控弹窗宿主，覆盖 UiDialog 的打开、关闭和焦点恢复路径。 */
function renderDialogHarness(options: { toolDetailVisible?: boolean, memberRunVisible?: boolean } = {}) {
  const Harness = defineComponent({
    components: { AgentConversationDialogs },
    template: `
      <button type="button" @click="toolDetailVisible = true">打开工具详情</button>
      <AgentConversationDialogs
        :tool-detail-visible="toolDetailVisible"
        :member-run-visible="memberRunVisible"
        :active-tool-detail="toolDetail"
        :active-member-runs="memberRuns"
        @update:tool-detail-visible="toolDetailVisible = $event"
        @update:member-run-visible="memberRunVisible = $event"
      />
    `,
    setup() {
      return {
        toolDetailVisible: ref(options.toolDetailVisible ?? false),
        memberRunVisible: ref(options.memberRunVisible ?? false),
        toolDetail: createToolDetail(),
        memberRuns: createMemberRuns(),
      }
    },
  })

  return render(Harness, {
    global: {
      stubs: {
        AgentConversationBody: defineComponent({
          name: 'AgentConversationBody',
          setup() {
            return () => h('div', '成员时间线')
          },
        }),
      },
    },
  })
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
    delegatedMemberRuns: [],
    attachments: [],
    inputAttachments: [],
    outputAttachments: [],
  }
}

/** 构造成员运行夹具，验证多成员切换与消息折叠状态。 */
function createMemberRuns(): AgentMemberRunItem[] {
  return [
    createMemberRun('member-run-1', '成员一', '第一个成员输入'),
    createMemberRun('member-run-2', '成员二', '第二个成员输入'),
  ]
}

/** 生成成员运行数据，时间线为空以避免测试耦合到时间线展示细节。 */
function createMemberRun(runId: string, name: string, input: string): AgentMemberRunItem {
  return {
    parent_run_id: 'parent-run-1',
    run_id: runId,
    agent_id: runId.replace('run', 'agent'),
    agent_name: name,
    status: 'completed',
    created_at: '2026-07-24T10:00:00+08:00',
    updated_at: '2026-07-24T10:01:00+08:00',
    delegate_tool_call_id: 'tool-call-1',
    input_prompt: input,
    output_prompt: `${name}输出`,
    timeline_items: [],
  }
}
