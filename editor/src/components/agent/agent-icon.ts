/**
 * 文件功能：集中维护智能体图标键与前端 lucide 图标、视觉样式的映射。
 */
import type { Component } from 'vue'
import { Blocks, Bot, Images, Sparkles } from 'lucide-vue-next'

interface AgentIconDefinition {
  component: Component
  shellClass: string
  activeShellClass: string
}

const DEFAULT_AGENT_ICON: AgentIconDefinition = {
  component: Bot,
  shellClass: 'bg-slate-100 text-slate-600 ring-slate-200',
  activeShellClass: 'bg-slate-700 text-white ring-slate-300',
}

const AGENT_ICON_DEFINITIONS: Record<string, AgentIconDefinition> = {
  'content-spark': {
    component: Sparkles,
    shellClass: 'bg-sky-50 text-sky-700 ring-sky-100',
    activeShellClass: 'bg-sky-600 text-white ring-sky-200',
  },
  'component-blocks': {
    component: Blocks,
    shellClass: 'bg-violet-50 text-violet-700 ring-violet-100',
    activeShellClass: 'bg-violet-600 text-white ring-violet-200',
  },
  'resource-images': {
    component: Images,
    shellClass: 'bg-emerald-50 text-emerald-700 ring-emerald-100',
    activeShellClass: 'bg-emerald-600 text-white ring-emerald-200',
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
