/** 文件功能：验证版本化放映入口拒绝旧产物及隐藏路由的旧字段，保留零完成停留。 */
import { describe, expect, it } from 'vitest'
import { assertSlideshowConfig, parseSceneAdvance, SlideshowConfigError } from './slideshow-config'

describe('schema 4 放映配置', () => {
  it('接受静态 fixture 和完整的新配置', () => {
    expect(() => assertSlideshowConfig({ routes: [] })).not.toThrow()
    expect(() => assertSlideshowConfig({ playback: { schemaVersion: 4, loop: true,
      advanceDefaults: { mode: 'scene_end', delayMs: 5000, completionDelayMs: 0 } }, routes: [] })).not.toThrow()
  })
  it.each([
    { playback: { autoStart: false } }, { playback: { schemaVersion: 3 } },
    { playback: { schemaVersion: 4, autoStart: false } },
    { playback: { schemaVersion: 4, advanceDefaults: { mode: 'timeline_end' } } },
    { routes: [{ meta: { hidden: true }, children: [{ meta: { advance: { mode: 'media_end' } } }] }] },
  ])('旧配置必须明确失败：%j', input => {
    try { assertSlideshowConfig(input); expect.fail('必须拒绝旧配置') }
    catch (error) { expect(error).toBeInstanceOf(SlideshowConfigError); expect(error).toHaveProperty('code', 'RUNTIME_SLIDESHOW_SCHEMA_UNSUPPORTED') }
  })
  it.each([null, -1, true, '0', 3600001])('拒绝非法完成停留：%j', completionDelayMs => {
    expect(() => parseSceneAdvance({ mode: 'scene_end', completionDelayMs })).toThrow(SlideshowConfigError)
  })
})
