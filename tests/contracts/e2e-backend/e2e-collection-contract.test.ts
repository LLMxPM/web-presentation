/**
 * 文件功能：以 --list 契约固定 Playwright project 的收集边界，并守护 E2E 侧 seed 版本与 Backend 一致。
 *
 * 依据 docs/developer/testing/e2e-redesign.md §3.6/验收标准 7：
 * - 默认 test:e2e 只收集 auth + smoke；regression 与 all 的收集数量由本测试固定；
 * - tests/e2e/helpers/e2e-env.ts 的 EXPECTED_SEED_VERSION 必须与 backend SEED_VERSION 同步演进。
 */
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

import { EXPECTED_SEED_VERSION } from '../../e2e/helpers/e2e-env'

const repoRoot = path.resolve(__dirname, '../../..')

interface ListedSpec {
  title: string
  file: string
  tests: Array<{ projectId: string }>
}

interface ListedSuite {
  specs?: ListedSpec[]
  suites?: ListedSuite[]
}

interface ListReport {
  suites?: ListedSuite[]
}

/** 递归展开 JSON 报告中的所有 spec。 */
function collectSpecs(suites: ListedSuite[]): ListedSpec[] {
  return suites.flatMap(suite => [...(suite.specs ?? []), ...collectSpecs(suite.suites ?? [])])
}

/** 执行 playwright --list 并按 project 统计收集到的用例数量；用 argv 直接调用 CLI，不经过 shell。 */
function countTestsByProject(): Record<string, number> {
  const playwrightCli = path.join(repoRoot, 'node_modules/@playwright/test/cli.js')
  const output = execFileSync(process.execPath, [playwrightCli, 'test', '--list', '--reporter=json'], {
    cwd: repoRoot,
    encoding: 'utf-8',
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  const report = JSON.parse(output) as ListReport
  const counts: Record<string, number> = {}
  for (const spec of collectSpecs(report.suites ?? [])) {
    for (const test of spec.tests) {
      counts[test.projectId] = (counts[test.projectId] ?? 0) + 1
    }
  }
  return counts
}

describe('E2E project 收集边界', () => {
  it('各 project 的收集数量必须与命令语义一致', () => {
    const counts = countTestsByProject()

    // auth + smoke 构成默认 test:e2e 的轻量核心链路。
    expect(counts['auth']).toBe(1)
    expect(counts['smoke']).toBe(6)
    // regression 范围为写型夹具、AI 真实链路与 Runtime 重型链路。
    expect(counts['visual-edit']).toBe(3)
    expect(counts['ai']).toBe(3)
    expect(counts['runtime-heavy']).toBe(1)
  })
})

describe('E2E seed 版本契约', () => {
  it('E2E 期望 seed 版本必须与 Backend test_data.py 一致', () => {
    const seedSource = fs.readFileSync(
      path.join(repoRoot, 'backend/app/scripts/test_data.py'),
      'utf-8',
    )
    const match = seedSource.match(/^SEED_VERSION\s*=\s*(\d+)/m)
    expect(match, 'backend/app/scripts/test_data.py 缺少 SEED_VERSION 常量').not.toBeNull()
    expect(Number(match![1])).toBe(EXPECTED_SEED_VERSION)
  })
})
