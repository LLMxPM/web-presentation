/** 文件功能：复用 E2E/全量测试的依赖、停服预演、端口复核与浏览器准备顺序。 */
import { ensureE2eDependencies, findOccupiedServices, installBrowsers, stopOccupiedServices } from './e2e-env.mjs'

/** 执行共同预检；可注入隔离操作验证顺序，默认实现只在显式选项开启时产生副作用。 */
export async function preflightE2e(options, {
  logPrefix = '[e2e-env]',
  ensureDependencies = ensureE2eDependencies,
  findOccupied = findOccupiedServices,
  stopOccupied = stopOccupiedServices,
  install = installBrowsers,
} = {}) {
  console.log(`${logPrefix} 检查 E2E 基础依赖...`)
  await ensureDependencies({ startInfra: options.startInfra, dryRun: options.dryRun, logPrefix })
  console.log(`${logPrefix} 检查服务端口（IPv4/IPv6）...`)
  const occupied = await findOccupied({ logPrefix })
  if (occupied.length > 0) {
    if (!options.stopServices) {
      throw new Error(`以下端口已被占用：${describePorts(occupied)}。确认属于本仓后加 --stop-services，或先执行 stop.mjs。`)
    }
    // 所有占用都能规划停止后才执行，未知占用在任何真实停服之前失败。
    stopOccupied(occupied, { dryRun: true, logPrefix })
    if (!options.dryRun) {
      stopOccupied(occupied, { dryRun: false, logPrefix })
      const remaining = await findOccupied({ logPrefix })
      if (remaining.length > 0) throw new Error(`停止后端口仍被占用：${describePorts(remaining)}；请检查自动重启或未知进程。`)
    }
  } else {
    console.log(`${logPrefix} 服务端口空闲`)
  }
  if (options.installBrowsers) install({ dryRun: options.dryRun, logPrefix })
}

/** 在报错中仅展示服务与端口，不输出连接串或凭据。 */
function describePorts(services) {
  return services.map((item) => `${item.label}:${item.port}`).join('、')
}
