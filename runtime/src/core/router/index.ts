/**
 * 文件用途：创建普通 Runtime 预览/开发路由，并注册平台预览宿主页。
 */

import type { RouteRecordRaw } from 'vue-router'

import { normalizeViewModulePath, resolvePreviewEntryModulePath } from '@/core/shared/runtime-preview'
import { getRuntimePreviewContext } from '@/core/utils/path'
import { createProjectRouter } from './project-router'

/**
 * 生成非构建态专用的预览宿主路由。
 * @returns 组件预览、资源预览与单页预览路由
 */
function buildPreviewHostRoutes(): RouteRecordRaw[] {
  const previewEntryDescriptor = getRuntimePreviewContext()?.entryDescriptor
  const previewEntryModulePath = resolvePreviewEntryModulePath(previewEntryDescriptor)
  const routes: RouteRecordRaw[] = []

  if (previewEntryModulePath) {
    const standalonePreviewFilePath = normalizeViewModulePath(previewEntryModulePath)
    const standaloneRoutePath = `/${previewEntryModulePath}`
    routes.push({
      path: standaloneRoutePath,
      name: '__standalone_preview',
      component: () => import('@/views/StandalonePreviewView.vue'),
      props: route => ({
        filePath: standalonePreviewFilePath,
        designWidth: Number(route.query.width) || undefined,
        designHeight: Number(route.query.height) || undefined,
      }),
      meta: { title: '单页预览' },
    })
  }

  routes.push({
    path: '/__component-preview',
    name: '__component_preview',
    component: () => import('@/views/component-preview/ComponentPreviewView.vue'),
    meta: { title: '组件预览' },
  })

  routes.push({
    path: '/__asset-preview',
    name: '__asset_preview',
    component: () => import('@/views/asset-preview/AssetPreviewView.vue'),
    meta: { title: '资源预览' },
  })

  return routes
}

/**
 * 异步创建完整 Runtime 路由器。
 * @returns Vue Router 实例
 */
async function createAppRouter() {
  return createProjectRouter({
    extraRoutes: buildPreviewHostRoutes(),
  })
}

export default createAppRouter()
