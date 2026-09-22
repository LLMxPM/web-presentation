/**
 * 文件用途：验证组件预览 schema 归一化逻辑，保证 Runtime 和 Editor 的预览参数契约稳定。
 */
import { describe, expect, it } from 'vitest'

import { normalizeComponentPreviewSchema } from './component-preview'

describe('normalizeComponentPreviewSchema', () => {
  it('应兼容 presets 中用 name 表示 key 的旧配置', () => {
    const schema = normalizeComponentPreviewSchema({
      presets: [
        {
          name: 'full-report',
          label: '完整报告',
          props: {
            title: '经营分析报告',
          },
        },
      ],
    })

    expect(schema?.presets?.[0]).toEqual(expect.objectContaining({
      key: 'full-report',
      name: 'full-report',
      label: '完整报告',
    }))
  })
})
