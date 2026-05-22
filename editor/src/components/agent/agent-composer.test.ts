/**
 * 文件功能：验证智能体输入组件的按钮态切换与快捷键发送行为。
 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it, vi } from 'vitest'

import AgentComposer from '@/components/agent/AgentComposer.vue'

describe('AgentComposer', () => {
  it('空闲态应展示发送按钮，并在回车时触发 action', async () => {
    const actionSpy = vi.fn()
    render(AgentComposer, {
      props: {
        modelValue: '帮我优化页面头图',
        placeholder: '请输入消息',
        onAction: actionSpy,
      },
    })

    const textarea = screen.getByPlaceholderText('请输入消息')
    expect(screen.getByRole('button', { name: '发送' })).toBeTruthy()

    await fireEvent.keyDown(textarea, { key: 'Enter' })
    expect(actionSpy).toHaveBeenCalledTimes(1)
  })

  it('运行态应展示停止按钮，并在禁用时阻止 action', async () => {
    const actionSpy = vi.fn()
    render(AgentComposer, {
      props: {
        modelValue: '',
        placeholder: '请输入消息',
        streaming: true,
        actionDisabled: true,
        onAction: actionSpy,
      },
    })

    const button = screen.getByRole('button', { name: '停止' })
    expect(button).toHaveProperty('disabled', true)

    await fireEvent.click(button)
    expect(actionSpy).not.toHaveBeenCalled()
  })

  it('运行态不应禁用文本输入，便于提前编辑下一条消息', () => {
    render(AgentComposer, {
      props: {
        modelValue: '下一条消息草稿',
        placeholder: '请输入消息',
        streaming: true,
      },
    })

    const textarea = screen.getByPlaceholderText('请输入消息')
    expect(textarea).toHaveProperty('disabled', false)
    expect(screen.getByRole('button', { name: '停止' })).toBeTruthy()
  })

  it('硬禁用态应禁用输入框和主按钮', () => {
    render(AgentComposer, {
      props: {
        modelValue: '不可编辑',
        placeholder: '请输入消息',
        disabled: true,
        actionDisabled: true,
      },
    })

    expect(screen.getByPlaceholderText('请输入消息')).toHaveProperty('disabled', true)
    expect(screen.getByRole('button', { name: '发送' })).toHaveProperty('disabled', true)
  })

  it('应在输入区展示上下文用量环，并点击展示 K 单位浮窗', async () => {
    const openSpy = vi.fn()
    render(AgentComposer, {
      props: {
        modelValue: '',
        placeholder: '请输入消息',
        contextUsedTokens: 3200,
        contextAvailableTokens: 6400,
        onContextUsageOpen: openSpy,
      },
    })

    const usage = screen.getByRole('button', { name: '上下文用量' })
    expect(usage).toBeTruthy()
    expect(usage).not.toHaveAttribute('title')

    await fireEvent.click(usage)

    expect(openSpy).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('dialog', { name: '上下文用量详情' })).toBeTruthy()
    expect(screen.getByText('已用上下文')).toBeTruthy()
    expect(screen.getByText('可用上下文')).toBeTruthy()
    expect(screen.getByText('3 K')).toBeTruthy()
    expect(screen.getByText('6 K')).toBeTruthy()

    await fireEvent.pointerDown(document.body)

    expect(screen.queryByRole('dialog', { name: '上下文用量详情' })).toBeNull()
  })

  it('待确认时应覆盖输入框，并只提交允许或忽略动作', async () => {
    const confirmSpy = vi.fn()
    const rejectSpy = vi.fn()
    render(AgentComposer, {
      props: {
        modelValue: '',
        placeholder: '请输入消息',
        pendingRequirement: {
          id: null,
          kind: 'confirmation',
          run_id: 'run-paused',
          session_id: 'session-1',
          tool_name: 'apply_page_edits',
          tool_execution: { tool_name: 'apply_page_edits', tool_call_id: 'tool-1', tool_args: { change_note: '改标题' } },
          suggested_patch: null,
          user_feedback_schema: [],
          note: null,
        },
        onHitlConfirm: confirmSpy,
        onHitlReject: rejectSpy,
      },
    })

    expect(screen.queryByPlaceholderText('请输入消息')).toBeNull()
    expect(screen.queryByText('确认备注')).toBeNull()
    expect(screen.getByText('允许执行 apply_page_edits 吗？')).toBeTruthy()

    await fireEvent.click(screen.getByRole('button', { name: /提交/ }))
    expect(confirmSpy).toHaveBeenCalledTimes(1)

    await fireEvent.click(screen.getByRole('button', { name: /忽略/ }))
    expect(rejectSpy).toHaveBeenCalledTimes(1)
  })

  it('结构化提问应支持多题切换、预设选项和自定义回答', async () => {
    const submitSpy = vi.fn()
    render(AgentComposer, {
      props: {
        modelValue: '',
        placeholder: '请输入消息',
        pendingRequirement: {
          id: 'requirement-1',
          kind: 'user_feedback',
          run_id: 'run-paused',
          session_id: 'session-1',
          tool_name: 'ask_user',
          tool_execution: { tool_name: 'ask_user', tool_call_id: 'tool-ask-1', requires_user_input: true },
          suggested_patch: null,
          user_feedback_schema: [
            {
              question: '这次优先调整哪个区域？',
              header: '范围',
              multi_select: true,
              selected_options: null,
              options: [
                { label: '首屏', description: '只调整第一屏。' },
                { label: '全页面', description: '整体调整。' },
              ],
            },
            {
              question: '视觉风格倾向是什么？',
              header: '风格',
              multi_select: false,
              selected_options: null,
              options: [
                { label: '克制', description: '信息密度更高。' },
                { label: '醒目', description: '视觉冲击更强。' },
              ],
            },
          ],
          note: null,
        },
        onHitlFeedbackSubmit: submitSpy,
      },
    })

    expect(screen.getByText('这次优先调整哪个区域？')).toBeTruthy()
    expect(screen.getByText('1 / 2')).toBeTruthy()
    expect(screen.getByRole('button', { name: /下一题/ })).toHaveProperty('disabled', true)

    await fireEvent.click(screen.getByText('首屏'))
    await fireEvent.click(screen.getByRole('button', { name: /下一题/ }))

    expect(screen.getByText('视觉风格倾向是什么？')).toBeTruthy()
    await fireEvent.update(screen.getByPlaceholderText('或直接输入自定义回答'), '保留当前图标风格')
    await fireEvent.click(screen.getByRole('button', { name: /上一题/ }))
    expect(screen.getByText('这次优先调整哪个区域？')).toBeTruthy()
    await fireEvent.click(screen.getByRole('button', { name: /下一题/ }))
    await fireEvent.click(screen.getByRole('button', { name: /提交/ }))

    expect(submitSpy).toHaveBeenCalledWith([
      { question: '这次优先调整哪个区域？', selected_label: '首屏', custom_text: null },
      { question: '视觉风格倾向是什么？', selected_label: null, custom_text: '保留当前图标风格' },
    ])
  })
})
