/**
 * 文件功能：验证内容助手活跃 Run 焦点状态的标题栏语义与液态球动画结构。
 */
import { render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import AgentScopeStatus from '@/components/agent/AgentScopeStatus.vue'

describe('AgentScopeStatus', () => {
  it('应展示 Run 焦点并提供前置液态球动画挂载点', () => {
    render(AgentScopeStatus, {
      props: {
        typeLabel: '页面',
        label: '经营概览',
        tooltip: '当前任务焦点：页面 · 经营概览',
      },
    })

    const status = screen.getByRole('status')
    expect(status).toHaveTextContent('页面')
    expect(status).toHaveTextContent('经营概览')
    expect(status).toHaveAttribute('title', '当前任务焦点：页面 · 经营概览')
    expect(status).toHaveClass('agent-scope-status')
    expect(status.querySelector('.agent-scope-orb')).toBeInTheDocument()
    expect(status.querySelector('.agent-scope-orb__fluid')).toBeInTheDocument()
    expect(status.querySelector('.agent-scope-orb__light')).toBeInTheDocument()
    expect(status.querySelector('.agent-scope-status__text-sheen')).toBeInTheDocument()
    expect(status.querySelector('.agent-scope-status__dot')).not.toBeInTheDocument()
  })
})
