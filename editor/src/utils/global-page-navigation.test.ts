/**
 * 文件功能：验证全局管理页面来源路径的构建、站内校验和工作空间识别。
 */
import { describe, expect, it } from 'vitest'

import {
  buildGlobalPageLocation,
  parseWorkspaceIdFromPath,
  resolveGlobalReturnPath,
} from '@/utils/global-page-navigation'

describe('global page navigation', () => {
  it('应携带当前工作空间页面作为全局页面返回来源', () => {
    expect(buildGlobalPageLocation('accountAiSettings', '/workspaces/7/projects/3/pages/9?mode=preview')).toEqual({
      name: 'accountAiSettings',
      query: { returnTo: '/workspaces/7/projects/3/pages/9?mode=preview' },
    })
  })

  it('应拒绝站外、协议相对和全局页面循环返回路径', () => {
    expect(resolveGlobalReturnPath('https://example.com')).toBeNull()
    expect(resolveGlobalReturnPath('//example.com/path')).toBeNull()
    expect(resolveGlobalReturnPath('/account/ai-settings?section=models')).toBeNull()
    expect(resolveGlobalReturnPath('/admin/users')).toBeNull()
  })

  it('应从合法工作空间路径提取正整数空间 ID', () => {
    expect(parseWorkspaceIdFromPath('/workspaces/17/assets')).toBe(17)
    expect(parseWorkspaceIdFromPath('/account/profile')).toBeNull()
    expect(parseWorkspaceIdFromPath('/workspaces/invalid/home')).toBeNull()
  })
})
