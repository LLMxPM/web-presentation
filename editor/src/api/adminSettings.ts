/**
 * 文件功能：封装平台系统设置管理 API，包括设置查询、批量更新与 S3 对象存储连通性测试。
 */
import { http } from '@/api/http'
import type {
  S3TestConnectionRequest,
  S3TestConnectionResponse,
  SystemSettingsListResponse,
} from '@/types/api'

/** 管理中心概况与配置页面共用快照，保存后即时更新 Safe-Mode 告警。 */
export const ADMIN_SETTINGS_QUERY_KEY = ['admin-settings'] as const

/** 获取平台全量系统设置列表及分类信息。 */
export async function fetchAdminSettings(): Promise<SystemSettingsListResponse> {
  const { data } = await http.get<SystemSettingsListResponse>('/v1/admin/settings')
  return data
}

/** 批量更新系统设置并触发热重载。 */
export async function updateAdminSettings(settings: Record<string, unknown>): Promise<SystemSettingsListResponse> {
  const { data } = await http.put<SystemSettingsListResponse>('/v1/admin/settings', { settings })
  return data
}

/** 测试 S3 兼容对象存储连通性。 */
export async function testS3StorageConnection(
  payload: S3TestConnectionRequest,
): Promise<S3TestConnectionResponse> {
  const { data } = await http.post<S3TestConnectionResponse>(
    '/v1/admin/settings/storage/test-connection',
    payload,
  )
  return data
}
