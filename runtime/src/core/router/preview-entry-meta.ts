/** 文件功能：解析候选与正式单页预览共用的标题和演讲者备注，不暴露未分配的页面 ID。 */
import type { RuntimePreviewArtifactManifest } from '@/core/shared/runtime-preview'

/** 从不可变 artifact 元数据构建单页宿主路由；旧 artifact 使用原默认标题。 */
export function previewEntryMeta(entryPage: RuntimePreviewArtifactManifest['entry_page']) {
  return { title: entryPage?.title || '单页预览', speakerNotes: entryPage?.speaker_notes || undefined }
}
