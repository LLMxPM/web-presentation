/** 文件功能：验证创建候选和正式页面的预览元数据一致，并兼容旧 artifact。 */
import { describe, expect, it } from 'vitest'
import { previewEntryMeta } from './preview-entry-meta'

describe('单页预览元数据', () => {
  it('候选和正式页面都读取实际标题与备注', () => {
    expect(previewEntryMeta({ code: 'PG1', title: '正式标题', speaker_notes: '演讲提示' }))
      .toEqual({ title: '正式标题', speakerNotes: '演讲提示' })
  })
  it('旧 artifact 保持默认标题', () => {
    expect(previewEntryMeta(undefined)).toEqual({ title: '单页预览', speakerNotes: undefined })
  })
})
