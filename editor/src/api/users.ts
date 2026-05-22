/**
 * 文件功能：封装平台用户管理 API。
 */
import { http } from '@/api/http'
import type { RecordStatus, UserItem, UserRole } from '@/types/api'

export interface UserCreatePayload {
  username: string
  password: string
  display_name: string
  role: UserRole
  status: RecordStatus
}

export interface UserUpdatePayload {
  display_name?: string
  role?: UserRole
  status?: RecordStatus
}

export async function listUsers() {
  const { data } = await http.get<UserItem[]>('/users')
  return data
}

export async function createUser(payload: UserCreatePayload) {
  const { data } = await http.post<UserItem>('/users', payload)
  return data
}

export async function updateUser(userId: number, payload: UserUpdatePayload) {
  const { data } = await http.patch<UserItem>(`/users/${userId}`, payload)
  return data
}

export async function resetUserPassword(userId: number, newPassword: string) {
  const { data } = await http.post<UserItem>(`/users/${userId}/reset-password`, { new_password: newPassword })
  return data
}
