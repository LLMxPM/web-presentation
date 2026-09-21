/**
 * 文件功能：封装平台级系统默认值的只读查询接口。
 */
import { http } from '@/api/http'

export interface DefaultStyleSpec {
  style_spec_markdown: string
}

export interface SystemSettings {
  app_timezone: string
}

/** 读取后端业务时区，使已构建的前端也能跟随部署配置。 */
export async function fetchSystemSettings(): Promise<SystemSettings> {
  const { data } = await http.get<SystemSettings>('/system/settings')
  return data
}

/** 获取平台级默认 Markdown 样式规范，供前端表单初始值使用。 */
export async function fetchDefaultStyleSpec(): Promise<DefaultStyleSpec> {
  const { data } = await http.get<DefaultStyleSpec>('/system/default-style-spec')
  return data
}
