/**
 * 文件用途：解析 Runtime 运行角色（all/preview/build/check），按角色推导插件面与执行预算，
 * 供 vite.config 插件选择、任务调度器与健康快照共用，避免角色语义散落多处。
 */

/** Runtime 运行角色：all 合并部署，preview/build/check 分角色部署。 */
export type RuntimeRole = 'all' | 'preview' | 'build' | 'check'

/** 调度任务类别：完整编译诊断、正式构建、轻量内部工具各自独立容量。 */
export type RuntimeViteTaskKind = 'diagnostics' | 'project' | 'light'

/** 单个任务类别的执行预算：并发上限、排队上限与排队超时。 */
export interface RuntimeTaskBudget {
  concurrency: number
  maxQueueSize: number
  queueWaitTimeoutMs: number
}

/** 角色启用的插件面；health 恒为 true，其余按角色裁剪。 */
export interface RuntimeRoleSurface {
  health: true
  /** 预览壳：独立预览门、Vue 转换与 SaaS 预览（含 snapdom 资源代理）。 */
  preview: boolean
  /** 正式构建入口 /__runtime_internal/v1/builds/project。 */
  projectBuild: boolean
  /** 编译诊断入口 /__runtime_internal/v1/diagnostics/artifact。 */
  checkDiagnostics: boolean
  /** 轻量内部工具：可视化编辑与资源比例测量。 */
  lightTools: boolean
}

const RUNTIME_ROLES: readonly RuntimeRole[] = ['all', 'preview', 'build', 'check']

const DEFAULT_VITE_TASK_CONCURRENCY = 1
const DEFAULT_VITE_TASK_QUEUE_SIZE = 16
const DEFAULT_VITE_TASK_QUEUE_WAIT_TIMEOUT_MS = 30000
const DEFAULT_LIGHT_TOOL_CONCURRENCY = 2
const DEFAULT_LIGHT_TOOL_QUEUE_SIZE = 32
const DEFAULT_LIGHT_TOOL_QUEUE_WAIT_TIMEOUT_MS = 5000
const DEFAULT_LIGHT_TOOL_TIMEOUT_MS = 10000

/**
 * 解析 Runtime 角色；空值回退 all，非法值在启动期直接抛错以便快速失败。
 * @param raw 环境变量 RUNTIME_ROLE 原始值
 * @returns 角色枚举
 */
export function resolveRuntimeRole(raw?: string | null): RuntimeRole {
  const normalized = String(raw || '').trim().toLowerCase()
  if (!normalized) {
    return 'all'
  }
  if ((RUNTIME_ROLES as readonly string[]).includes(normalized)) {
    return normalized as RuntimeRole
  }
  throw new Error(`非法 RUNTIME_ROLE：${raw}。可选值：${RUNTIME_ROLES.join(' | ')}`)
}

/**
 * 读取当前进程角色（环境变量 RUNTIME_ROLE）。
 */
export function getRuntimeRole(env: NodeJS.ProcessEnv = process.env): RuntimeRole {
  return resolveRuntimeRole(env.RUNTIME_ROLE)
}

/**
 * 推导角色启用的插件面；preview 不得开放构建、诊断与轻量工具入口。
 * @param role 运行角色
 * @returns 插件面开关
 */
export function resolveRuntimeRoleSurface(role: RuntimeRole): RuntimeRoleSurface {
  switch (role) {
    case 'preview':
      return {
        health: true,
        preview: true,
        projectBuild: false,
        checkDiagnostics: false,
        lightTools: false,
      }
    case 'build':
      return {
        health: true,
        preview: false,
        projectBuild: true,
        checkDiagnostics: false,
        lightTools: false,
      }
    case 'check':
      return {
        health: true,
        preview: false,
        projectBuild: false,
        checkDiagnostics: true,
        lightTools: true,
      }
    default:
      return {
        health: true,
        preview: true,
        projectBuild: true,
        checkDiagnostics: true,
        lightTools: true,
      }
  }
}

/**
 * 解析指定任务类别的执行预算。
 * 优先级：类别专用变量 → 角色级 RUNTIME_{ROLE}_VITE_TASK_* 覆盖 → 共享 RUNTIME_VITE_TASK_* → 默认值。
 * @param kind 任务类别
 * @param role 运行角色
 * @param env 环境变量表（测试可注入）
 * @returns 该类别的并发、排队上限与排队超时
 */
export function resolveRuntimeKindBudget(
  kind: RuntimeViteTaskKind,
  role: RuntimeRole,
  env: NodeJS.ProcessEnv = process.env,
): RuntimeTaskBudget {
  if (kind === 'light') {
    return {
      concurrency: readPositiveInt(env, ['RUNTIME_LIGHT_TOOL_CONCURRENCY'], DEFAULT_LIGHT_TOOL_CONCURRENCY),
      maxQueueSize: readPositiveInt(env, ['RUNTIME_LIGHT_TOOL_QUEUE_SIZE'], DEFAULT_LIGHT_TOOL_QUEUE_SIZE),
      queueWaitTimeoutMs: readPositiveInt(
        env,
        ['RUNTIME_LIGHT_TOOL_QUEUE_WAIT_TIMEOUT_MS'],
        DEFAULT_LIGHT_TOOL_QUEUE_WAIT_TIMEOUT_MS,
      ),
    }
  }

  const kindPrefix = kind === 'diagnostics' ? 'RUNTIME_VITE_DIAGNOSTICS' : 'RUNTIME_VITE_PROJECT'
  const sharedFallback = role === 'all'
    ? ['RUNTIME_VITE_TASK']
    : [`RUNTIME_${role.toUpperCase()}_VITE_TASK`, 'RUNTIME_VITE_TASK']

  return {
    concurrency: readPositiveInt(
      env,
      [`${kindPrefix}_CONCURRENCY`, ...sharedFallback.map(prefix => `${prefix}_CONCURRENCY`)],
      DEFAULT_VITE_TASK_CONCURRENCY,
    ),
    maxQueueSize: readPositiveInt(
      env,
      [`${kindPrefix}_QUEUE_SIZE`, ...sharedFallback.map(prefix => `${prefix}_QUEUE_SIZE`)],
      DEFAULT_VITE_TASK_QUEUE_SIZE,
    ),
    queueWaitTimeoutMs: readPositiveInt(
      env,
      [`${kindPrefix}_QUEUE_WAIT_TIMEOUT_MS`, ...sharedFallback.map(prefix => `${prefix}_QUEUE_WAIT_TIMEOUT_MS`)],
      DEFAULT_VITE_TASK_QUEUE_WAIT_TIMEOUT_MS,
    ),
  }
}

/**
 * 解析轻量工具单次执行时限；超时返回结构化 504。
 */
export function resolveLightToolTimeoutMs(env: NodeJS.ProcessEnv = process.env): number {
  return readPositiveInt(env, ['RUNTIME_LIGHT_TOOL_TIMEOUT_MS'], DEFAULT_LIGHT_TOOL_TIMEOUT_MS)
}

/**
 * 按名称顺序读取第一个合法正整数环境变量，否则返回默认值。
 */
function readPositiveInt(env: NodeJS.ProcessEnv, names: string[], fallback: number): number {
  for (const name of names) {
    const parsed = Number(String(env[name] || '').trim())
    if (Number.isInteger(parsed) && parsed > 0) {
      return parsed
    }
  }
  return fallback
}
