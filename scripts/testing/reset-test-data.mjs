/**
 * 文件功能：调用 backend 测试数据 CLI，清理平台冒烟测试过程中写入的 smoke 场景数据。
 */
import { spawn } from 'node:child_process'
import { resolve } from 'node:path'
import { buildE2eBackendEnv } from './e2e-database-env.mjs'

const child = spawn('uv', ['run', '--project', '.', 'python', '-m', 'app.scripts.reset_test_data'], {
  cwd: resolve(process.cwd(), 'backend'),
  stdio: 'inherit',
  shell: process.platform === 'win32',
  env: buildE2eBackendEnv(),
})

child.on('exit', (code) => {
  process.exitCode = code ?? 1
})
