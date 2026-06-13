/**
 * 文件功能：验证组件引用关系弹窗的默认勾选、状态展示和批量升级提交。
 */
import { defineComponent, h } from 'vue'
import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import ComponentReferenceDialog from '@/components/component-preview/ComponentReferenceDialog.vue'
import type { WorkspaceComponentItem, WorkspaceComponentReferences } from '@/types/api'

describe('ComponentReferenceDialog', () => {
  it('默认勾选待升级引用并提交页面与组件 ID', async () => {
    const { emitted } = renderDialog()

    expect(screen.getByText('页面引用')).toBeInTheDocument()
    expect(screen.getByText('组件引用')).toBeInTheDocument()
    expect(screen.getByText(/草稿已升级，待发布/)).toBeInTheDocument()

    await fireEvent.click(screen.getByText('更新选中引用'))

    expect(emitted().upgrade[0]).toEqual([{ page_ids: [101], component_ids: [201] }])
  })

  it('清空选择后应禁用更新按钮', async () => {
    renderDialog()

    await fireEvent.click(screen.getByText('清空选择'))

    expect(screen.getByText('更新选中引用')).toHaveProperty('disabled', true)
  })
})

function renderDialog() {
  return render(ComponentReferenceDialog, {
    props: {
      modelValue: true,
      component: createComponent(),
      references: createReferences(),
      loading: false,
      upgrading: false,
    },
    global: {
      stubs: {
        teleport: true,
        BaseDialog: createBaseDialogStub(),
        BaseButton: createBaseButtonStub(),
      },
    },
  })
}

function createBaseDialogStub() {
  return defineComponent({
    name: 'BaseDialog',
    props: {
      modelValue: {
        type: Boolean,
        default: false,
      },
    },
    emits: ['update:modelValue'],
    setup(props, { slots }) {
      return () => props.modelValue
        ? h('section', [
          slots.default?.(),
          h('footer', slots.footer?.()),
        ])
        : null
    },
  })
}

function createBaseButtonStub() {
  return defineComponent({
    name: 'BaseButton',
    props: {
      disabled: {
        type: Boolean,
        default: false,
      },
      loading: {
        type: Boolean,
        default: false,
      },
    },
    emits: ['click'],
    setup(props, { emit, slots }) {
      return () => h(
        'button',
        {
          type: 'button',
          disabled: props.disabled || props.loading,
          onClick: () => emit('click'),
        },
        slots.default?.(),
      )
    },
  })
}

function createComponent(): WorkspaceComponentItem {
  return {
    id: 9,
    workspace_id: 1,
    workspace_name: '工作空间',
    code: 'CMP009',
    name: '目标组件',
    import_name: 'TargetCard',
    component_type: '内容组件',
    summary: null,
    status: 'active',
    content: '<template><div /></template>',
    preview_schema: null,
    current_version_no: 3,
    draft_base_version_no: 3,
    has_unpublished_changes: false,
    published_at: '2026-05-01T10:00:00+08:00',
    file_type: 'vue',
    created_at: '2026-05-01T10:00:00+08:00',
    updated_at: '2026-05-01T10:00:00+08:00',
    created_by: 1,
    updated_by: 1,
  }
}

function createReferences(): WorkspaceComponentReferences {
  return {
    component_id: 9,
    component_code: 'CMP009',
    current_version_no: 3,
    page_references: [
      {
        page_id: 101,
        page_code: 'PAGE101',
        page_title: '旧版页面',
        project_id: 11,
        project_name: '演示项目',
        current_version_no: 2,
        page_version_id: 1001,
        referenced_component_version_no: 1,
        is_current_version: false,
        can_upgrade: true,
      },
      {
        page_id: 102,
        page_code: 'PAGE102',
        page_title: '新版页面',
        project_id: 11,
        project_name: '演示项目',
        current_version_no: 1,
        page_version_id: 1002,
        referenced_component_version_no: 3,
        is_current_version: true,
        can_upgrade: false,
      },
    ],
    component_references: [
      {
        component_id: 201,
        component_code: 'CMP201',
        component_name: '旧版组件',
        current_version_no: 1,
        component_version_id: 2001,
        referenced_component_version_no: 1,
        has_unpublished_changes: false,
        draft_referenced_component_version_no: 1,
        draft_is_current_version: false,
        is_current_version: false,
        can_upgrade: true,
      },
      {
        component_id: 202,
        component_code: 'CMP202',
        component_name: '草稿已升级组件',
        current_version_no: 1,
        component_version_id: 2002,
        referenced_component_version_no: 1,
        has_unpublished_changes: true,
        draft_referenced_component_version_no: 3,
        draft_is_current_version: true,
        is_current_version: false,
        can_upgrade: false,
      },
    ],
  }
}
