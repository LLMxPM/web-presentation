/**
 * 文件功能：提供平台级默认样式规范的只读缓存，作为表单初始值的统一来源。
 * 模块加载时即发起请求，后续所有组件复用同一份缓存结果。
 */
import { ref } from 'vue'

import { fetchDefaultStyleSpec } from '@/api/system'

const cached = ref('')

fetchDefaultStyleSpec().then(
  (spec) => {
    cached.value = spec.style_spec_markdown
  },
  () => {
    cached.value = ''
  },
)

export function useDefaultStyleSpec() {
  return { defaultStyleSpecMarkdown: cached }
}
