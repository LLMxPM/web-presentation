/**
 * 文件用途：验证页面模块加载策略在 preview 与 build release 模式下的分流逻辑。
 */

import { afterEach, describe, expect, it } from 'vitest'

import type { RuntimePreloadedConfigBundle } from '@/core/shared/runtime-preview'
import { setRuntimePreloadedConfig } from '@/core/utils/path'

import {
  shouldUseBuildReleaseLocalViewModule,
  shouldUseLocalRuntimeViewModule,
} from './view-module'

describe('view module load strategy', () => {
  afterEach(() => {
    setRuntimePreloadedConfig(undefined)
  })

  it('runtime 本地模式应允许加载视图目录与本地示例页面', () => {
    expect(shouldUseLocalRuntimeViewModule('src/views/PG20260412001.vue')).toBe(true)
    expect(shouldUseLocalRuntimeViewModule('src/examples/local/views/defaultpage/HomePage.vue')).toBe(true)
    expect(shouldUseLocalRuntimeViewModule('src/runtime-shell/fallback/NotFoundPage.vue')).toBe(false)
    expect(shouldUseLocalRuntimeViewModule('src/components/demo.vue')).toBe(false)
  })

  it('build release 应允许 manifest 命中的业务页面按本地构建模块加载', () => {
    const preloadedConfig: RuntimePreloadedConfigBundle = {
      manifest: {
        artifact_id: '405',
        artifact_kind: 'build_release',
        tenant_id: 'tenant_1',
        preview_kind: 'project',
        owner_scope: {
          scope_type: 'project',
          workspace_id: '1',
          project_id: '2',
        },
        entry_descriptor: {
          entry_type: 'route',
          route: '/page-7',
        },
        modules: {
          'src/views/PG20260412001.vue': {
            path: 'src/views/PG20260412001.vue',
            hash: 'sha256:6a78a3c4',
          },
        },
        assets: {},
      },
    }

    expect(
      shouldUseBuildReleaseLocalViewModule('src/views/PG20260412001.vue', preloadedConfig),
    ).toBe(true)
    expect(
      shouldUseBuildReleaseLocalViewModule('src/runtime-shell/fallback/NotFoundPage.vue', preloadedConfig),
    ).toBe(false)
    expect(
      shouldUseBuildReleaseLocalViewModule('src/views/PG20260411001.vue', preloadedConfig),
    ).toBe(false)
    expect(
      shouldUseLocalRuntimeViewModule('src/views/PG20260412001.vue', preloadedConfig),
    ).toBe(false)
    expect(
      shouldUseLocalRuntimeViewModule('src/examples/local/views/defaultpage/HomePage.vue', preloadedConfig),
    ).toBe(false)
  })
})
