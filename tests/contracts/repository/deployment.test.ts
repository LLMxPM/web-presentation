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

it('全部交付 Dockerfile 均进入发布与镜像验证矩阵', () => {
  const dockerfiles = execFileSync('git', ['ls-files', '--', '*Dockerfile*'], { encoding: 'utf8' }).trim().split('\n')
  const smoke = yaml('.github/workflows/platform-test.yml').jobs['platform-image-build-smoke'].strategy.matrix.include
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

it('Compose 的共享凭据位置与部署配置目录一致', () => {
  for (const filename of fs.readdirSync('deploy/compose').filter(name => name.endsWith('.yml'))) {
    const file = path.join('deploy/compose', filename)
    const compose = yaml(file)
    expect(path.resolve(path.dirname(file), compose.secrets.render_service_credential.file))
      .toBe(path.resolve('deploy/secrets/render_service_credential'))
    for (const service of Object.values(compose.services) as any[]) {
      for (const envFile of service.env_file ?? []) {
        expect(fs.existsSync(path.resolve(path.dirname(file), `${envFile}.example`))).toBe(true)
      }
    }
  }
})

it('Runtime 共享依赖变更必须触发其 PR 门禁', () => {
  const job = yaml('.github/workflows/platform-test.yml').jobs['detect-runtime-change']
  const filterStep = job.steps.find((step: any) => step.with?.filters)
  const filters: string[] = parse(filterStep.with.filters).runtime_changed
  for (const dependency of ['package.json', 'pnpm-lock.yaml', 'pnpm-workspace.yaml']) {
    expect(filters, dependency).toContain(dependency)
  }
})
