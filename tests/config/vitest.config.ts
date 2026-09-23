/**
 * 文件功能：定义根仓跨模块契约测试的 Vitest 配置，只收集根级 contracts 测试。
 */
import { fileURLToPath } from 'node:url'

import { defineConfig } from 'vitest/config'

const repoRoot = fileURLToPath(new URL('../../', import.meta.url))

export default defineConfig({
  root: repoRoot,
  test: {
    environment: 'node',
    include: ['tests/contracts/**/*.test.ts'],
    globals: true,
  },
})
