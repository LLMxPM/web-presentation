/** 文件功能：校验交付镜像、Compose 文件引用与共享 workspace 输入的 CI 覆盖边界。 */
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { parse } from 'yaml'
import { expect, it } from 'vitest'

/** 读取 YAML 配置作为结构化对象，避免依赖注释或文件排版。 */
function yaml(file: string) {
  return parse(fs.readFileSync(file, 'utf8'))
}

/**
 * 读取分级脚本正文。镜像 smoke 矩阵与路径判定规则都由该脚本产出，
 * workflow 里只剩 `${{ fromJSON(...) }}`，因此契约断言必须落在脚本源码上。
 */
function scopeScript() {
  return fs.readFileSync('.github/scripts/resolve-test-scope.sh', 'utf8')
}

/** 从脚本的 FULL_MATRIX 单行 JSON 解析出全量镜像构建条目。 */
function fullImageMatrix() {
  const raw = scopeScript().match(/readonly FULL_MATRIX='(\[[^\n]*\])'/)?.[1]
  if (!raw) {
    throw new Error('未能在 resolve-test-scope.sh 中找到 FULL_MATRIX 定义。')
  }
  return JSON.parse(raw) as Array<{ name: string; file: string; tag: string; cache_scope: string }>
}

it('全部交付 Dockerfile 均进入发布与镜像验证矩阵', () => {
  // docs 内的历史构建配方仅是证据；实际交付目录仍逐文件检查发布与执行门禁。
  const dockerfiles = execFileSync('git', ['ls-files', '--', '*Dockerfile*'], { encoding: 'utf8' })
    .trim().split('\n').filter(file => file && !file.startsWith('docs/'))
  const smoke = fullImageMatrix()
  const releaseJobs = Object.values(yaml('.github/workflows/platform-release.yml').jobs) as any[]
  const published = releaseJobs.flatMap(job => [
    ...(job.strategy?.matrix?.include ?? []).map((entry: any) => entry.file),
    ...(job.steps ?? []).map((step: any) => step.with?.file),
  ])
  for (const file of dockerfiles) {
    expect(smoke.map((entry: any) => entry.file), file).toContain(file)
    expect(published, file).toContain(file)
  }
})

/**
 * 分级脚本按路径命中决定要不要重建某个镜像变体，正则一旦与镜像实际打包的输入脱节，
 * PR 门禁就会漏掉受影响变体；这里要求四类变体各自至少有一条路径规则覆盖。
 */
it('镜像 smoke 分级为每个交付变体保留路径触发规则', () => {
  const script = scopeScript()
  for (const name of ['platform_re', 'runtime_re', 'renderer_re']) {
    expect(script, name).toMatch(new RegExp(`^${name}='\\^`, 'm'))
  }
  expect(script).toContain('FULL_MATRIX')
})

it('Compose 的共享凭据位置与部署配置目录一致', () => {
  for (const filename of fs.readdirSync('deploy/compose').filter(name => name.endsWith('.yml'))) {
    const file = path.join('deploy/compose', filename)
    const compose = yaml(file)
    if (compose.secrets?.render_service_credential) {
      expect(path.resolve(path.dirname(file), compose.secrets.render_service_credential.file))
        .toBe(path.resolve('deploy/secrets/render_service_credential'))
    }
    for (const service of Object.values(compose.services) as any[]) {
      for (const envFile of service.env_file ?? []) {
        expect(fs.existsSync(path.resolve(path.dirname(file), `${envFile}.example`))).toBe(true)
      }
    }
  }
})

it('Runtime 共享依赖变更必须触发其 PR 门禁', () => {
  const runtimeRe = scopeScript().match(/^runtime_re='([^']+)'$/m)?.[1]
  expect(runtimeRe).toBeTruthy()
  for (const dependency of ['package.json', 'pnpm-lock.yaml', 'pnpm-workspace.yaml']) {
    expect(runtimeRe!, dependency).toContain(dependency.replaceAll('.', '\\.'))
  }
})

it('门禁范围由 test-scope job 调用分级脚本产出', () => {
  const job = yaml('.github/workflows/platform-test.yml').jobs['test-scope']
  expect(job).toBeTruthy()
  const step = job.steps.find((entry: any) => entry.run)
  expect(step.run).toContain('.github/scripts/resolve-test-scope.sh')
  // dorny/paths-filter 在 push/schedule 事件没有 base 时恒为真，已被脚本取代，不得回归。
  expect(JSON.stringify(job)).not.toContain('paths-filter')
})
