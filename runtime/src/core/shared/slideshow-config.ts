/** 文件功能：定义 schema 4 放映配置的严格读入边界，旧产物明确失败，不静默变换推进模式。 */
import type { PageAdvanceConfig } from '@/core/types/page-transition'

export const RUNTIME_SLIDESHOW_SCHEMA_VERSION = 4
export const DEFAULT_SCENE_ADVANCE: PageAdvanceConfig = { mode: 'manual', delayMs: 5000, completionDelayMs: 300 }

/** 配置失败有稳定原因码，可要求重新生成旧预览或构建产物。 */
export class SlideshowConfigError extends Error {
  readonly code = 'RUNTIME_SLIDESHOW_SCHEMA_UNSUPPORTED'
  constructor() { super('放映配置不兼容当前 schema 4，请重新生成预览或构建产物。') }
}

/** 只保留定时与实际完成后停留；缺省仅表示继承，不表示旧协议兼容。 */
export function parseSceneAdvance(value: unknown, fallback: PageAdvanceConfig = DEFAULT_SCENE_ADVANCE): PageAdvanceConfig {
  if (value == null) return { ...fallback, completionDelayMs: fallback.completionDelayMs ?? 300 }
  if (typeof value !== 'object' || Array.isArray(value)) throw new SlideshowConfigError()
  const input = value as Record<string, unknown>
  const delay = input.delayMs === undefined ? 5000 : input.delayMs
  const completion = input.completionDelayMs === undefined ? 300 : input.completionDelayMs
  if (Object.keys(input).some(key => !['mode', 'delayMs', 'completionDelayMs'].includes(key))
    || !['manual', 'timer', 'scene_end'].includes(String(input.mode))
    || !Number.isInteger(delay) || (delay as number) < 1000 || (delay as number) > 3600000
    || !Number.isInteger(completion) || (completion as number) < 0 || (completion as number) > 3600000) throw new SlideshowConfigError()
  return { mode: input.mode as PageAdvanceConfig['mode'], delayMs: delay as number, completionDelayMs: completion as number }
}

/** Backend 下发与本地 fixture 的 playback 都必须携带版本；静态组件 fixture 可以没有放映配置。 */
export function assertSlideshowConfig(config: unknown): void {
  if (!config || typeof config !== 'object') throw new SlideshowConfigError()
  const source = config as { playback?: unknown; routes?: unknown }
  let advance = DEFAULT_SCENE_ADVANCE
  if (source.playback != null) {
    const playback = source.playback as Record<string, unknown>
    if (typeof playback !== 'object' || Array.isArray(playback) || playback.schemaVersion !== 4
      || Object.keys(playback).some(key => !['schemaVersion', 'loop', 'advanceDefaults'].includes(key))
      || (playback.loop !== undefined && typeof playback.loop !== 'boolean')) throw new SlideshowConfigError()
    advance = parseSceneAdvance(playback.advanceDefaults)
  }
  /** 验证所有叶子覆盖，不能让旧模式通过未访问的页面潜伏到正式播放才回退。 */
  function visit(routes: unknown): void {
    if (!Array.isArray(routes)) return
    for (const route of routes) {
      if (!route || typeof route !== 'object') continue
      parseSceneAdvance(route.meta?.advance, advance)
      visit(route.children)
    }
  }
  visit(source.routes)
}
