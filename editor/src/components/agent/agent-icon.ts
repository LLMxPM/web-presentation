/**
 * 文件功能：集中维护智能体图标键与前端 lucide 图标、视觉样式的映射。
 */
import type { Component } from 'vue'
import { Blocks, Bot, Images, Sparkles } from '@lucide/vue'

interface AgentIconDefinition {
  component: Component
  shellClass: string
  activeShellClass: string
}

const DEFAULT_AGENT_ICON: AgentIconDefinition = {
  component: Bot,
  shellClass: 'bg-surface-muted text-text-secondary ring-border',
  activeShellClass: 'bg-surface-inverse-raised text-text-inverse ring-border-strong',
}

const AGENT_ICON_DEFINITIONS: Record<string, AgentIconDefinition> = {
  'content-spark': {
    component: Sparkles,
    shellClass: 'bg-info-muted text-info-strong ring-info-border',
    activeShellClass: 'bg-info text-text-inverse ring-info-border',
  },
  'component-blocks': {
    component: Blocks,
    shellClass: 'bg-ai-muted text-ai-strong ring-ai-border',
    activeShellClass: 'bg-ai text-text-inverse ring-ai-border',
  },
  'resource-images': {
    component: Images,
    shellClass: 'bg-success-muted text-success-strong ring-success-border',
    activeShellClass: 'bg-success text-text-inverse ring-success-border',
  },
}

/** 根据后端图标 key 返回可渲染的 lucide 组件。 */
export function resolveAgentIconComponent(icon: string | null | undefined): Component {
  return resolveAgentIconDefinition(icon).component
}

/** 根据后端图标 key 返回图标容器色彩，选中态用于强调当前智能体。 */
export function getAgentIconShellClass(icon: string | null | undefined, active = false): string {
  const definition = resolveAgentIconDefinition(icon)
  return active ? definition.activeShellClass : definition.shellClass
}

/** 读取图标定义；未知 key 保持可用的默认机器人图标。 */
function resolveAgentIconDefinition(icon: string | null | undefined): AgentIconDefinition {
  const normalizedIcon = String(icon || '').trim()
  return AGENT_ICON_DEFINITIONS[normalizedIcon] ?? DEFAULT_AGENT_ICON
}
