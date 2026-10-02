/**
 * 文件功能：AdminSettingsView 系统设置管理视图交互与连通性测试单测。
 */
import { render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import AdminSettingsView from '@/views/AdminSettingsView.vue'
import * as adminSettingsApi from '@/api/adminSettings'
import type { SystemSettingsListResponse } from '@/types/api'

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: { returnTo: '/workspaces/1/home' } }),
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('@/utils/message', () => ({
  Message: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  },
}))

const mockSettingsData: SystemSettingsListResponse = {
  items: [
    {
      key: 'asset_storage_driver',
      category: 'storage',
      description: '对象存储驱动',
      value: 'local',
      is_secret: false,
      is_env_overridden: false,
      source: 'default',
    },
    {
      key: 's3_bucket',
      category: 'storage',
      description: 'S3 存储桶',
      value: 'test-bucket',
      is_secret: false,
      is_env_overridden: false,
      source: 'default',
    },
    {
      key: 'app_name',
      category: 'general',
      description: '平台名称',
      value: '页面管理后台',
      is_secret: false,
      is_env_overridden: true,
      source: 'env',
    },
    {
      key: 'app_timezone',
      category: 'general',
      description: '时区',
      value: 'Asia/Shanghai',
      is_secret: false,
      is_env_overridden: false,
      source: 'default',
    },
  ],
  categories: [
    {
      category: 'storage',
      category_name: '存储管理',
      items: [],
    },
    {
      category: 'general',
      category_name: '常规设置',
      items: [],
    },
    {
      category: 'security',
      category_name: '安全策略',
      items: [],
    },
    {
      category: 'ai',
      category_name: 'AI 运营',
      items: [],
    },
    {
      category: 'diagnostic',
      category_name: '系统诊断',
      items: [],
    },
  ],
  safe_mode_warnings: [
    {
      key: 'corrupted_key',
      error: '非法值降级',
      fallback_value: 'default_val',
    },
  ],
}

describe('AdminSettingsView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.spyOn(adminSettingsApi, 'fetchAdminSettings').mockResolvedValue(mockSettingsData)
  })

  it('挂载后应获取设置列表并渲染 Safe-Mode 警告与 5 个分类标签', async () => {
    const { unmount } = render(AdminSettingsView)

    await waitFor(() => {
      expect(adminSettingsApi.fetchAdminSettings).toHaveBeenCalled()
      expect(screen.getByText('系统设置')).toBeTruthy()
      expect(screen.getByText('系统已触发 Safe-Mode 安全降级防护')).toBeTruthy()
    })

    expect(screen.getByText(/corrupted_key/)).toBeTruthy()
    expect(screen.getByText('存储管理')).toBeTruthy()
    expect(screen.getByText('常规设置')).toBeTruthy()
    expect(screen.getByText('安全策略')).toBeTruthy()
    expect(screen.getByText('AI 运营')).toBeTruthy()
    expect(screen.getByText('系统诊断')).toBeTruthy()

    unmount()
  })
})
