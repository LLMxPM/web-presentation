/**
 * 文件功能：验证 Runtime 预览上传目录的拼装逻辑，避免生成不在 Runtime 白名单内的目标路径。
 */

import { describe, expect, it } from 'vitest'

import { buildRuntimePreviewTargetPath } from '@/utils/runtime-files'

describe('runtime preview target path', () => {
  it('应始终生成 src/views 下的预览目录', () => {
    expect(buildRuntimePreviewTargetPath(12, '2026-03-30')).toBe('src/views/2026-03-30/12')
  })

  it('应在缺失用户标识时回退到 anonymous 目录', () => {
    expect(buildRuntimePreviewTargetPath('', '2026-03-30')).toBe('src/views/2026-03-30/anonymous')
  })
})
