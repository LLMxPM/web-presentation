/**
 * 文件功能：定义根仓平台级 E2E 冒烟测试配置，统一管理基础地址、失败产物与浏览器策略。
 */
import { defineConfig, devices } from '@playwright/test'

const baseURL = process.env.E2E_BASE_URL || 'http://127.0.0.1:5173'

export default defineConfig({
  testDir: './tests/e2e/specs',
  timeout: 120_000,
  fullyParallel: false,
  reporter: [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  outputDir: 'test-results/playwright',
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
      },
    },
  ],
})
