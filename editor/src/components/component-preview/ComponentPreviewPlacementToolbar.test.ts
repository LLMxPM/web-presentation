/**
 * 文件功能：验证组件预览占位工具条的内联布局与配置回传。
 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import ComponentPreviewPlacementToolbar from '@/components/component-preview/ComponentPreviewPlacementToolbar.vue'
import { buildDefaultComponentPreviewOptions } from '@/components/component-preview/preview-config'
import type { ComponentPreviewOptions } from '@/types/api'

describe('ComponentPreviewPlacementToolbar', () => {
  it('内联模式应展示全部占位字段并回传配置更新', async () => {
    const { emitted } = render(ComponentPreviewPlacementToolbar, {
      props: {
        modelValue: buildDefaultComponentPreviewOptions(),
        embedded: true,
        inline: true,
      },
    })

    expect(screen.getByText('宽度')).toBeInTheDocument()
    expect(screen.getByText('高度')).toBeInTheDocument()
    expect(screen.getByText('水平')).toBeInTheDocument()
    expect(screen.getByText('垂直')).toBeInTheDocument()
    expect(screen.getByText('留白')).toBeInTheDocument()

    await fireEvent.update(screen.getAllByRole('textbox')[0], '80')
    const updates = emitted()['update:modelValue'] as Array<[ComponentPreviewOptions]>
    expect(updates[updates.length - 1][0].placement.width_value).toBe(80)

    await fireEvent.click(screen.getByText('默认'))
    expect(emitted()['reset-defaults']).toHaveLength(1)
  })
})
