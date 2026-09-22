/**
 * 文件用途：定义 Runtime Kit 公开能力清单的 TypeScript 类型。
 */

export type RuntimeKitExportKind = 'component' | 'composable' | 'util' | 'type'
export type RuntimeKitCapabilityAudience = 'backend' | 'agent'
export type RuntimeKitRecommendationLevel = 'default' | 'advanced' | 'internal-only'

export interface RuntimeKitCapabilityDoc {
  usage?: string[]
  returns?: string
  return_example?: string[]
  constraints?: string[]
  audiences?: RuntimeKitCapabilityAudience[]
}

export interface RuntimeKitExportItem {
  kind: RuntimeKitExportKind
  base_name: string
  version_no: number
  name: string
  import_path: string
  category: string
  description: string
  capability?: RuntimeKitCapability
}

export interface RuntimeKitCapability extends RuntimeKitCapabilityDoc {
  enabled: boolean
  previewable?: boolean
  recommendation_level?: RuntimeKitRecommendationLevel
  display_name?: string
  summary?: string
  tags?: string[]
  preview_schema?: Record<string, unknown>
  preview_options?: Record<string, unknown>
}

export interface RuntimeKitManifest {
  version: string
  alias: '@runtime-kit'
  exports: RuntimeKitExportItem[]
}
