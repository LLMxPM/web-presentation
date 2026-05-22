/**
 * 文件功能：管理工作空间组件草稿表单、校验、未保存变更判断和创建/更新保存流程。
 */
import { computed, reactive, ref } from 'vue'

import { createComponent, updateComponent } from '@/api/catalog'
import type { RecordStatus, WorkspaceComponentItem, WorkspaceComponentType } from '@/types/api'

export const DEFAULT_WORKSPACE_COMPONENT_TYPE: WorkspaceComponentType = '内容区块'
export const workspaceComponentTypeValues: WorkspaceComponentType[] = [
  '整页模板',
  '布局容器',
  '内容区块',
  '数据展示',
  '资源渲染',
  '样式能力',
  '路由能力',
]
const IMPORT_NAME_PATTERN = /^[A-Z][A-Za-z0-9]{0,63}$/

export interface WorkspaceComponentDraftForm {
  name: string
  import_name: string
  component_type: WorkspaceComponentType
  summary: string
  status: RecordStatus
  content: string
  preview_schema: string
}

export interface WorkspaceComponentDraftErrors {
  name: string
  import_name: string
  component_type: string
  content: string
  preview_schema: string
}

interface DraftOptions {
  workspaceId: () => number | null
}

/**
 * 创建工作空间组件草稿状态，供右侧工作台和编辑面板共享。
 * @param options 工作空间上下文读取器
 */
export function useWorkspaceComponentDraft(options: DraftOptions) {
  const currentComponent = ref<WorkspaceComponentItem | null>(null)
  const form = reactive<WorkspaceComponentDraftForm>(createEmptyForm())
  const errors = reactive<WorkspaceComponentDraftErrors>(createEmptyErrors())

  const isEditMode = computed(() => Boolean(currentComponent.value))
  const hasUnsavedSourceChanges = computed(() => {
    const component = currentComponent.value
    if (!component) {
      return Boolean(
        form.name.trim()
        || form.import_name.trim()
        || form.summary.trim()
        || form.content.trim()
        || form.preview_schema.trim(),
      )
    }

    return (
      form.name !== component.name
      || form.import_name !== component.import_name
      || form.component_type !== component.component_type
      || form.summary !== (component.summary || '')
      || form.status !== component.status
      || form.content !== component.content
      || normalizeComparableText(form.preview_schema) !== normalizeComparableText(component.preview_schema)
    )
  })

  /**
   * 用完整表单对象覆盖当前草稿，供纯 UI 编辑组件通过 update:form 回写。
   * @param nextForm 新表单值
   */
  function replaceForm(nextForm: WorkspaceComponentDraftForm): void {
    form.name = nextForm.name
    form.import_name = nextForm.import_name
    form.component_type = normalizeComponentType(nextForm.component_type)
    form.summary = nextForm.summary
    form.status = nextForm.status
    form.content = nextForm.content
    form.preview_schema = nextForm.preview_schema
  }

  /**
   * 进入新建组件状态，清空组件引用和全部表单错误。
   */
  function resetForCreate(): void {
    currentComponent.value = null
    replaceForm(createEmptyForm())
    clearErrors()
  }

  /**
   * 从后端组件详情恢复草稿表单。
   * @param component 当前选中的工作空间组件
   */
  function loadFromComponent(component: WorkspaceComponentItem): void {
    currentComponent.value = component
    form.name = component.name
    form.import_name = component.import_name
    form.component_type = normalizeComponentType(component.component_type)
    form.summary = component.summary || ''
    form.status = component.status
    form.content = component.content
    form.preview_schema = component.preview_schema || ''
    clearErrors()
  }

  /**
   * 保存当前草稿。已有组件走更新，新建组件走创建。
   * @returns 保存后的组件；校验失败时返回 null
   */
  async function saveDraft(): Promise<WorkspaceComponentItem | null> {
    const normalizedPreviewSchema = normalizePreviewSchemaInput()
    if (!validateDraft(normalizedPreviewSchema)) {
      return null
    }

    const component = currentComponent.value
    let savedComponent: WorkspaceComponentItem
    if (component) {
      savedComponent = await updateComponent(component.id, {
        name: form.name,
        import_name: form.import_name.trim(),
        component_type: form.component_type,
        summary: form.summary || null,
        status: form.status,
        content: form.content,
        preview_schema: normalizedPreviewSchema,
      })
    } else {
      const workspaceId = options.workspaceId()
      if (!workspaceId) {
        errors.name = '缺少工作空间信息，无法创建组件。'
        return null
      }
      savedComponent = await createComponent({
        workspace_id: workspaceId,
        name: form.name,
        import_name: form.import_name.trim(),
        component_type: form.component_type,
        summary: form.summary || null,
        status: form.status,
        content: form.content,
        preview_schema: normalizedPreviewSchema,
        file_type: 'vue',
      })
    }

    loadFromComponent(savedComponent)
    return savedComponent
  }

  /**
   * 校验并归一化 previewSchema 输入，空白内容表示未配置。
   * @returns 可提交给后端的 JSON 文本；校验失败时返回 null
   */
  function normalizePreviewSchemaInput(): string | null {
    errors.preview_schema = ''
    const rawValue = form.preview_schema.trim()
    if (!rawValue) {
      return null
    }

    try {
      const parsedValue = JSON.parse(rawValue)
      if (!parsedValue || Array.isArray(parsedValue) || typeof parsedValue !== 'object') {
        errors.preview_schema = 'previewSchema 必须是 JSON 对象。'
        return null
      }
      return JSON.stringify(parsedValue, null, 2)
    } catch (error) {
      errors.preview_schema = error instanceof Error
        ? `previewSchema JSON 解析失败：${error.message}`
        : 'previewSchema JSON 解析失败。'
      return null
    }
  }

  /**
   * 校验表单核心字段，写入对应错误信息。
   * @param normalizedPreviewSchema 已归一化的 previewSchema
   */
  function validateDraft(normalizedPreviewSchema: string | null): boolean {
    errors.name = form.name.trim() ? '' : '必填'
    errors.import_name = validateImportName(form.import_name)
    errors.component_type = isWorkspaceComponentType(form.component_type) ? '' : '请选择有效组件类型'
    errors.content = form.content.trim() ? '' : '源码不能为空'
    if (form.preview_schema.trim() && !normalizedPreviewSchema && !errors.preview_schema) {
      errors.preview_schema = 'previewSchema JSON 解析失败。'
    }
    return !errors.name && !errors.import_name && !errors.component_type && !errors.content && !errors.preview_schema
  }

  /**
   * 清空全部表单错误。
   */
  function clearErrors(): void {
    errors.name = ''
    errors.import_name = ''
    errors.component_type = ''
    errors.content = ''
    errors.preview_schema = ''
  }

  return {
    currentComponent,
    errors,
    form,
    hasUnsavedSourceChanges,
    isEditMode,
    clearErrors,
    loadFromComponent,
    normalizePreviewSchemaInput,
    replaceForm,
    resetForCreate,
    saveDraft,
  }
}

/**
 * 判断输入是否属于固定组件分类。
 * @param value 待判断值
 */
export function isWorkspaceComponentType(value: unknown): value is WorkspaceComponentType {
  return workspaceComponentTypeValues.includes(value as WorkspaceComponentType)
}

/**
 * 归一化组件分类，非法值回退到默认内容区块。
 * @param value 原始组件分类
 */
export function normalizeComponentType(value: unknown): WorkspaceComponentType {
  return isWorkspaceComponentType(value) ? value : DEFAULT_WORKSPACE_COMPONENT_TYPE
}

/**
 * 判断组件分类是否应使用零留白预览。
 * @param value 原始组件分类
 */
export function usesZeroPaddingComponentPreview(value: unknown): value is '整页模板' | '布局容器' {
  return value === '整页模板' || value === '布局容器'
}

function createEmptyForm(): WorkspaceComponentDraftForm {
  return {
    name: '',
    import_name: '',
    component_type: DEFAULT_WORKSPACE_COMPONENT_TYPE,
    summary: '',
    status: 'active',
    content: '',
    preview_schema: '',
  }
}

function createEmptyErrors(): WorkspaceComponentDraftErrors {
  return {
    name: '',
    import_name: '',
    component_type: '',
    content: '',
    preview_schema: '',
  }
}

function normalizeComparableText(value: string | null | undefined): string {
  return String(value || '').trim()
}

function validateImportName(value: string): string {
  const normalizedValue = value.trim()
  if (!normalizedValue) {
    return '必填'
  }
  if (!IMPORT_NAME_PATTERN.test(normalizedValue)) {
    return '需使用 PascalCase 英文标识符，如 SalesMetricCard'
  }
  return ''
}
