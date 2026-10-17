/** 文件功能：回归停服规划的目录边界、父进程追溯、未知 PID 强制停止和 netstat 监听筛选。 */
import { describe, expect, it } from 'vitest'
import { collectRoots, findRoot, hasBlockedEntry, isRepoOwned, isServiceWrapper, planService } from '../../../.agents/skills/dev-start-test/scripts/lib/stop-plan.mjs'
import { parseNetstatListeners } from '../../../.agents/skills/dev-start-test/scripts/lib/system-processes.mjs'

const repoRoot = 'C:\\code\\wp\\web-presentation'
const target = { key: 'backend', label: 'Backend', port: 8000, local: true }

/** 构造隔离进程记录，测试只生成计划，不查询或停止真实进程。 */
function proc(pid: number, ppid: number, commandLine: string, name = 'node.exe') {
  return { pid, ppid, commandLine, name }
}

describe('仓库归属与启动链', () => {
  it.each([
    [`node "${repoRoot}\\scripts\\dev.mjs"`, true],
    [`"${repoRoot}\\.venv\\Scripts\\python.exe" -m uvicorn app.main:app`, true],
    ['node --cwd=C:/CODE/wp/web-presentation/editor dev', true],
    [`node "${repoRoot}-cli/scripts/dev.mjs"`, false],
    [`node "${repoRoot}-mcp/scripts/dev.mjs"`, false],
    [`node "${repoRoot}-backup/scripts/dev.mjs"`, false],
    ['node C:/elsewhere/C:/code/wp/web-presentation/dev.mjs', false],
    [`node "${repoRoot}/../another-project/dev.mjs"`, false],
    ['', false],
  ])('路径 %s 的归属应为 %s', (commandLine, owned) => {
    expect(isRepoOwned({ commandLine }, repoRoot)).toBe(owned)
  })

  it('兼容带空格路径，并保持 POSIX 大小写语义', () => {
    expect(isRepoOwned({ commandLine: 'node "C:/my work/repo/app.mjs"' }, 'C:/my work/repo')).toBe(true)
    expect(isRepoOwned({ commandLine: 'node /work/Repo/app.mjs' }, '/work/repo')).toBe(false)
  })

  it.each([
    ['uv run --project backend uvicorn app.main:app --reload', 'uv.exe', true],
    ['node C:/tools/pnpm.cjs --dir editor dev', 'node.exe', true],
    ['node "C:/Program Files/tools/pnpm.mjs" --filter web-runtime-vue dev', 'node.exe', true],
    [`"${repoRoot}/.venv/Scripts/python.exe" -m uvicorn app.main:app --reload`, 'python.exe', true],
    [`"${repoRoot}/.venv/Scripts/python.exe" "${repoRoot}/.venv/Scripts/uvicorn.exe" app.main:app`, 'python.exe', true],
    [`node "${repoRoot}/scripts/test-driver.mjs" -- uv run --project backend uvicorn app.main:app`, 'node.exe', false],
    ['cmd /c uv run --project backend uvicorn app.main:app', 'cmd.exe', false],
    ['uv run --project backend python maintenance.py', 'uv.exe', false],
  ])('仅识别实际服务启动器 %s', (commandLine, name, expected) => {
    expect(isServiceWrapper({ commandLine, name })).toBe(expected)
  })

  it('追溯到 pnpm 后停止，不把通用本仓编排进程作为整树根', () => {
    const driver = proc(9001, 0, `node "${repoRoot}/scripts/test-driver.mjs"`)
    const wrapper = proc(9002, 9001, 'node C:/tools/pnpm.cjs --dir editor dev')
    const listener = proc(9003, 9002, `node "${repoRoot}/node_modules/vite/bin/vite.js"`)
    expect(findRoot(listener, new Map([driver, wrapper, listener].map((item) => [item.pid, item])), []).pid).toBe(wrapper.pid)
  })

  it('不能跨越调用者，也不能在父进程环中无限追溯', () => {
    const listener = proc(9004, 9005, `node "${repoRoot}/editor/vite.js"`)
    const wrapper = proc(9005, 9004, 'node C:/tools/pnpm.cjs --dir editor dev')
    const processes = new Map([listener, wrapper].map((item) => [item.pid, item]))
    expect(findRoot(listener, processes, [wrapper.pid]).pid).toBe(listener.pid)
    expect(findRoot(listener, processes, []).pid).toBe(wrapper.pid)
  })
})

describe('未知监听与强制计划', () => {
  it('默认拒绝读不到信息的监听，显式 force 才生成可执行树根', () => {
    const snapshot = { listeners: [{ port: 8000, pid: 9100 }], processes: new Map() }
    const normal = planService(target, snapshot, { repoRoot })
    expect(hasBlockedEntry(normal)).toBe(true)
    expect(collectRoots([normal])).toEqual([])
    const forced = planService(target, snapshot, { repoRoot, force: true })
    expect(hasBlockedEntry(forced)).toBe(false)
    expect(collectRoots([forced])).toEqual([{ pid: 9100, services: ['Backend'] }])
  })

  it('同名前缀仓库默认拒绝，强制时也不追溯它的父进程', () => {
    const listener = proc(9201, 9200, `node "${repoRoot}-cli/dev.mjs"`)
    const parent = proc(9200, 0, 'node C:/tools/pnpm.cjs --dir editor dev')
    const snapshot = { listeners: [{ port: 8000, pid: listener.pid }], processes: new Map([[9200, parent], [9201, listener]]) }
    expect(hasBlockedEntry(planService(target, snapshot, { repoRoot }))).toBe(true)
    expect(collectRoots([planService(target, snapshot, { repoRoot, force: true })])[0].pid).toBe(listener.pid)
  })

  it('远程目标不停止本地同端口进程，双栈相同 PID 只处理一次', () => {
    const snapshot = { listeners: [{ port: 8000, pid: 9300 }, { port: 8000, pid: 9300 }], processes: new Map() }
    expect(planService({ ...target, local: false }, snapshot, { repoRoot, force: true }).entries).toEqual([])
    expect(collectRoots([planService(target, snapshot, { repoRoot, force: true })])).toHaveLength(1)
  })
})

it('netstat 只接收目标端口的 LISTENING，并去重 IPv4/IPv6', () => {
  const output = [
    'TCP 127.0.0.1:8000 0.0.0.0:0 LISTENING 9400',
    'TCP [::1]:8000 [::]:0 LISTENING 9400',
    'TCP 127.0.0.1:8000 127.0.0.1:55321 ESTABLISHED 9401',
    'TCP 127.0.0.1:8000 127.0.0.1:55322 TIME_WAIT 0',
    'UDP 127.0.0.1:8000 *:* 9402',
    'TCP 127.0.0.1:9999 0.0.0.0:0 LISTENING 9403',
  ].join('\r\n')
  expect(parseNetstatListeners(output, [8000])).toEqual([{ port: 8000, pid: 9400 }])
})
