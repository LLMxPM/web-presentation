/**
 * 文件功能：定义后台管理路由与鉴权守卫，引入分层的上下文路由视图。
 */
import { createRouter, createWebHistory } from 'vue-router'
import type { RouteLocation } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { buildWorkspaceHomePath } from '@/utils/workspace-routes'

/**
 * 将旧工作空间项目列表入口重定向到新的空间首页路由。
 * @param to 当前匹配到的旧路由
 */
function redirectToWorkspaceHome(to: RouteLocation): string {
  const rawWorkspaceId = to.params.workspaceId
  const workspaceId = Array.isArray(rawWorkspaceId) ? rawWorkspaceId[0] : rawWorkspaceId
  return buildWorkspaceHomePath(workspaceId ?? '')
}

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { guestOnly: true },
  },
  {
    path: '/',
    component: () => import('@/layouts/AdminLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      { path: '', component: () => import('@/views/EntryView.vue') },
      {
        path: 'workspaces/:workspaceId/home',
        name: 'workspaceHome',
        component: () => import('@/views/ProjectsView.vue'),
        meta: { workspaceNav: 'projects' },
      },
      {
        path: 'workspaces/:workspaceId/projects',
        redirect: redirectToWorkspaceHome,
      },
      {
        path: 'workspaces/:workspaceId/components',
        name: 'components',
        component: () => import('@/views/ComponentsView.vue'),
        meta: { fullHeight: true, workspaceNav: 'components' },
      },
      {
        path: 'workspaces/:workspaceId/assets',
        name: 'assets',
        component: () => import('@/views/AssetsView.vue'),
        meta: { fullHeight: true, workspaceNav: 'assets' },
      },
      {
        path: 'workspaces/:workspaceId/themes',
        name: 'themes',
        component: () => import('@/views/ThemesView.vue'),
        meta: { fullHeight: true, workspaceNav: 'themes' },
      },
      {
        path: 'workspaces/:workspaceId/styles',
        name: 'workspaceStyles',
        component: () => import('@/views/WorkspaceStylesView.vue'),
        meta: { fullHeight: true, workspaceNav: 'styles' },
      },

      { 
        path: 'workspaces/:workspaceId/projects/:projectId/pages',
        name: 'pages',
        component: () => import('@/views/PagesView.vue'),
        meta: { fullHeight: true, workspaceNav: 'projects' },
      },
      { 
        path: 'workspaces/:workspaceId/projects/:projectId/pages/:pageId',
        name: 'pageDetail',
        component: () => import('@/views/PageDetailView.vue'),
        meta: { workspaceNav: 'projects' },
      },
      {
        path: 'workspaces/:workspaceId/:pathMatch(.*)*',
        name: 'workspaceNotFound',
        component: () => import('@/views/NotFoundView.vue'),
      },
      {
        path: 'account/ai-settings',
        name: 'accountAiSettings',
        component: () => import('@/views/AccountAiSettingsView.vue'),
        meta: { hideSidebars: true },
      },
      {
        path: 'admin/users',
        name: 'users',
        component: () => import('@/views/UsersView.vue'),
        meta: { hideSidebars: true, platformAdmin: true },
      },
      {
        path: ':pathMatch(.*)*',
        name: 'notFound',
        component: () => import('@/views/NotFoundView.vue'),
      },
    ],
  },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const authStore = useAuthStore()
  await authStore.ensureLoaded()

  if (to.meta.requiresAuth && !authStore.user) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  if (to.meta.platformAdmin && authStore.user?.role !== 'platform_admin') {
    return { path: '/' }
  }

  if (to.meta.guestOnly && authStore.user) {
    return { path: '/' }
  }

  return true
})
