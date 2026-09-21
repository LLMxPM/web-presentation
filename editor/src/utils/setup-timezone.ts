/** 文件功能：在应用挂载前读取后端业务时区，统一部署环境下的时间展示。 */
import { fetchSystemSettings } from '@/api/system'
import { logClientWarning } from '@/utils/client-logger'
import { setAppTimezone } from '@/utils/timezone'

/** 成功时使用后端时区；网络不可用时保留构建配置或默认上海时区以便应用启动。 */
export async function initializeAppTimezone(): Promise<void> {
  try {
    const settings = await fetchSystemSettings()
    setAppTimezone(settings.app_timezone)
  } catch (error) {
    logClientWarning('读取业务时区失败，使用前端默认时区。', error)
  }
}
