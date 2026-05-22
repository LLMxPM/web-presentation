/**
 * 文件功能：封装 Editor 测试常用的 render 入口，统一挂载 Pinia 与 Vue Query。
 */
import { render, type RenderOptions } from '@testing-library/vue'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia } from 'pinia'

/**
 * 使用仓库内统一的测试插件组合渲染 Vue 组件。
 * @param component 待测试组件
 * @param options 透传给 testing-library 的额外配置
 * @returns 渲染结果
 */
export function renderWithEditorProviders<C>(component: C, options: RenderOptions<C> = {}) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  return render(component, {
    ...options,
    global: {
      plugins: [
        createPinia(),
        [VueQueryPlugin, { queryClient }] as [typeof VueQueryPlugin, { queryClient: QueryClient }],
      ],
      ...(options.global ?? {}),
    },
  })
}
