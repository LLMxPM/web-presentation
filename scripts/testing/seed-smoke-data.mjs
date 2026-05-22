/**
 * 文件功能：调用 backend 测试数据 CLI，为平台冒烟测试准备确定性 smoke 场景数据。
 */
import { spawn } from 'node:child_process'
import { resolve } from 'node:path'

const child = spawn('uv', ['run', '--project', '.', 'python', '-m', 'app.scripts.seed_test_data', '--scenario', 'smoke'], {
  cwd: resolve(process.cwd(), 'backend'),
  stdio: 'inherit',
  shell: process.platform === 'win32',
  env: {
    ...process.env,
    AI_TEST_MODE: process.env.AI_TEST_MODE || 'mock',
  },
})

child.on('exit', (code) => {
  process.exitCode = code ?? 1
})
