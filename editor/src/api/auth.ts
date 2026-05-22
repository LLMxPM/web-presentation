/**
 * 文件功能：封装认证相关 API，请求当前用户、登录、登出和修改密码。
 */
import { http } from '@/api/http'
import type { AuthUser, PreviewSizePreset } from '@/types/api'

export async function login(payload: { username: string; password: string }) {
  const { data } = await http.post<{ user: AuthUser }>('/auth/login', payload)
  return data
}

export async function logout() {
  const { data } = await http.post<{ message: string }>('/auth/logout')
  return data
}

export async function fetchMe() {
  const { data } = await http.get<AuthUser>('/auth/me')
  return data
}

export async function changePassword(payload: { old_password: string; new_password: string }) {
  const { data } = await http.post<{ message: string }>('/auth/change-password', payload)
  return data
}

/** 更新当前用户维护的预设尺寸 JSON。 */
export async function updatePreviewSizePresets(presets: PreviewSizePreset[]) {
  const { data } = await http.patch<AuthUser>('/auth/me/preview-size-presets', { presets })
  return data
}
