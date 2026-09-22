<template>
  <DefaultContentPage title="主题系统展示" subtitle="基于Tailwind扩展的变量，随着主题设置而变化">
    <template #content>
      <div class="space-y-8 p-6">
        <!-- 文本色系统展示 -->
        <section class="bg-background-subtle border border-border-subtle rounded-lg p-6">
          <div class="flex items-center mb-6">
            <Icon name="star" class="mr-3 text-primary" />
            <h2 class="font-heading text-2xl font-bold text-primary">文本色系统</h2>
          </div>

          <!-- Primary 文本色 -->
          <div class="mb-6">
            <h3 class="font-heading text-lg font-semibold text-primary mb-3">Primary 文本色（完整色阶）</h3>
            <div class="grid grid-cols-2 md:grid-cols-5 lg:grid-cols-11 gap-2">
              <div class="text-center">
                <div class="bg-primary text-white p-3 rounded text-sm font-medium">Default</div>
                <span class="text-xs text-secondary mt-1 block">primary</span>
              </div>
              <div class="text-center">
                <div class="bg-primary-50 text-primary-900 p-3 rounded text-sm font-medium">50</div>
                <span class="text-xs text-secondary mt-1 block">primary-50</span>
              </div>
              <div class="text-center">
                <div class="bg-primary-100 text-primary-900 p-3 rounded text-sm font-medium">100</div>
                <span class="text-xs text-secondary mt-1 block">primary-100</span>
              </div>
              <div class="text-center">
                <div class="bg-primary-200 text-primary-900 p-3 rounded text-sm font-medium">200</div>
                <span class="text-xs text-secondary mt-1 block">primary-200</span>
              </div>
              <div class="text-center">
                <div class="bg-primary-300 text-primary-900 p-3 rounded text-sm font-medium">300</div>
                <span class="text-xs text-secondary mt-1 block">primary-300</span>
              </div>
              <div class="text-center">
                <div class="bg-primary-400 text-white p-3 rounded text-sm font-medium">400</div>
                <span class="text-xs text-secondary mt-1 block">primary-400</span>
              </div>
              <div class="text-center">
                <div class="bg-primary-500 text-white p-3 rounded text-sm font-medium">500</div>
                <span class="text-xs text-secondary mt-1 block">primary-500</span>
              </div>
              <div class="text-center">
                <div class="bg-primary-600 text-white p-3 rounded text-sm font-medium">600</div>
                <span class="text-xs text-secondary mt-1 block">primary-600</span>
              </div>
              <div class="text-center">
                <div class="bg-primary-700 text-white p-3 rounded text-sm font-medium">700</div>
                <span class="text-xs text-secondary mt-1 block">primary-700</span>
              </div>
              <div class="text-center">
                <div class="bg-primary-800 text-white p-3 rounded text-sm font-medium">800</div>
                <span class="text-xs text-secondary mt-1 block">primary-800</span>
              </div>
              <div class="text-center">
                <div class="bg-primary-900 text-white p-3 rounded text-sm font-medium">900</div>
                <span class="text-xs text-secondary mt-1 block">primary-900</span>
              </div>
            </div>
          </div>

          <!-- Secondary 和 Tertiary 文本色 -->
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <h3 class="font-heading text-lg font-semibold text-secondary mb-3">Secondary 文本色</h3>
              <div class="space-y-2">
                <div class="flex items-center justify-between bg-background p-3 rounded border">
                  <span class="text-secondary">Secondary 默认</span>
                  <code class="text-xs bg-tertiary-100 px-2 py-1 rounded">text-secondary</code>
                </div>
                <div class="flex items-center justify-between bg-background p-3 rounded border">
                  <span class="text-secondary-300">Secondary 300</span>
                  <code class="text-xs bg-tertiary-100 px-2 py-1 rounded">text-secondary-300</code>
                </div>
                <div class="flex items-center justify-between bg-background p-3 rounded border">
                  <span class="text-secondary-700">Secondary 700</span>
                  <code class="text-xs bg-tertiary-100 px-2 py-1 rounded">text-secondary-700</code>
                </div>
              </div>
            </div>
            <div>
              <h3 class="font-heading text-lg font-semibold text-primary mb-3">Invert 文本色</h3>
              <div class="space-y-2">
                <div class="flex items-center justify-between bg-background-invert p-3 rounded border">
                  <span class="text-invert">Invert 默认</span>
                  <code class="text-invert text-xs  px-2 py-1 rounded">text-invert</code>
                </div>
                <div class="flex items-center justify-between bg-background-invert p-3 rounded border">
                  <span class="text-invert-400">Invert 400</span>
                  <code class="text-invert text-xs  px-2 py-1 rounded">text-invert-400</code>
                </div>
                <div class="flex items-center justify-between bg-background-invert p-3 rounded border">
                  <span class="text-invert-600">Invert 600</span>
                  <code class="text-invert text-xs  px-2 py-1 rounded">text-invert-600</code>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- 背景色系统展示 -->
        <section class="bg-background-subtle border border-border-subtle rounded-lg p-6">
          <div class="flex items-center mb-6">
            <Icon name="star" class="mr-3 size-5 text-primary" />
            <h2 class="font-heading text-2xl font-bold text-primary">背景色系统</h2>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <!-- Background 色阶 -->
            <div>
              <h3 class="font-heading text-lg font-semibold text-primary mb-3">Background 色阶</h3>
              <div class="space-y-2">
                <div class="bg-background border border-border p-4 rounded">
                  <span class="text-primary">默认背景 (bg-background)</span>
                </div>
                <div class="bg-background-100 border border-border p-4 rounded">
                  <span class="text-primary">背景 100 (bg-background-100)</span>
                </div>
                <div class="bg-background-300 border border-border p-4 rounded">
                  <span class="text-primary">背景 300 (bg-background-300)</span>
                </div>
                <div class="bg-background-500 border border-border p-4 rounded">
                  <span class="text-primary">背景 500 (bg-background-500)</span>
                </div>
                <div class="bg-background-700 border border-border p-4 rounded">
                  <span class="text-primary">背景 700 (bg-background-700)</span>
                </div>
              </div>
            </div>

            <!-- Background invert 色阶 -->
            <div>
              <h3 class="font-heading text-lg font-semibold text-primary mb-3">Background invert 色阶</h3>
              <div class="space-y-2">
                <div class="bg-background-invert border border-border p-4 rounded">
                  <span class="text-invert">反色背景 (bg-background-invert)</span>
                </div>
                <div class="bg-background-invert-100 border border-border p-4 rounded">
                  <span class="text-invert-100">反色背景 100 (bg-background-invert-100)</span>
                </div>
                <div class="bg-background-invert-300 border border-border p-4 rounded">
                  <span class="text-invert-300">反色背景 300 (bg-background-invert-300)</span>
                </div>
                <div class="bg-background-invert-500 border border-border p-4 rounded">
                  <span class="text-invert-500">反色背景 500 (bg-background-invert-500)</span>
                </div>
                <div class="bg-background-invert-700 border border-border p-4 rounded">
                  <span class="text-invert-700">反色背景 700 (bg-background-invert-700)</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- 边框色系统展示 -->
        <section class="bg-background-subtle border border-border-subtle rounded-lg p-6">
          <div class="flex items-center mb-6">
            <Icon name="star" class="mr-3 size-5 text-primary" />
            <h2 class="font-heading text-2xl font-bold text-primary">边框色系统</h2>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <h3 class="font-heading text-lg font-semibold text-primary mb-3">Border 边框色</h3>
              <div class="space-y-3">
                <div class="bg-background p-4 rounded border-2 border-border">
                  <span class="text-primary">默认边框 (border-border)</span>
                </div>
                <div class="bg-background p-4 rounded border-2 border-border-200">
                  <span class="text-primary">边框 200 (border-border-200)</span>
                </div>
                <div class="bg-background p-4 rounded border-2 border-border-400">
                  <span class="text-primary">边框 400 (border-border-400)</span>
                </div>
                <div class="bg-background p-4 rounded border-2 border-border-600">
                  <span class="text-primary">边框 600 (border-border-600)</span>
                </div>
              </div>
            </div>
            <div>
              <h3 class="font-heading text-lg font-semibold text-primary mb-3">Border Subtle 边框色</h3>
              <div class="space-y-3">
                <div class="bg-background p-4 rounded border-2 border-border-subtle">
                  <span class="text-primary">次级边框 (border-border-subtle)</span>
                </div>
                <div class="bg-background p-4 rounded border-2 border-border-subtle-300">
                  <span class="text-primary">次级边框 300 (border-border-subtle-300)</span>
                </div>
                <div class="bg-background p-4 rounded border-2 border-border-subtle-500">
                  <span class="text-primary">次级边框 500 (border-border-subtle-500)</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- 链接色系统展示 -->
        <section class="bg-background-subtle border border-border-subtle rounded-lg p-6">
          <div class="flex items-center mb-6">
            <Icon name="star" class="mr-3 size-5 text-primary" />
            <h2 class="font-heading text-2xl font-bold text-primary">链接色系统</h2>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div>
              <h3 class="font-heading text-lg font-semibold text-primary mb-3">默认链接色</h3>
              <div class="space-y-2">
                <a href="#" class="text-link block hover:text-link-hover">默认链接 (text-link)</a>
                <a href="#" class="text-link-300 block hover:text-link-hover-300">链接 300 (text-link-300)</a>
                <a href="#" class="text-link-700 block hover:text-link-hover-700">链接 700 (text-link-700)</a>
              </div>
            </div>
            <div>
              <h3 class="font-heading text-lg font-semibold text-primary mb-3">悬浮链接色</h3>
              <div class="space-y-2">
                <span class="text-link-hover block">悬浮链接色 (text-link-hover)</span>
                <span class="text-link-hover-400 block">悬浮链接 400 (text-link-hover-400)</span>
                <span class="text-link-hover-600 block">悬浮链接 600 (text-link-hover-600)</span>
              </div>
            </div>
            <div>
              <h3 class="font-heading text-lg font-semibold text-primary mb-3">已访问链接色</h3>
              <div class="space-y-2">
                <span class="text-link-visited block">已访问链接 (text-link-visited)</span>
                <span class="text-link-visited-400 block">已访问 400 (text-link-visited-400)</span>
                <span class="text-link-visited-600 block">已访问 600 (text-link-visited-600)</span>
              </div>
            </div>
          </div>
        </section>

        <!-- 强调色系统展示 -->
        <section class="bg-background-subtle border border-border-subtle rounded-lg p-6">
          <div class="flex items-center mb-6">
            <Icon name="star" class="mr-3 size-5 text-primary" />
            <h2 class="font-heading text-2xl font-bold text-primary">强调色系统</h2>
          </div>

          <!-- 六个强调色展示 -->
          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <!-- Accent1 -->
            <div class="space-y-3">
              <h3 class="font-heading text-lg font-semibold text-accent1">Accent1 强调色</h3>
              <div class="space-y-2">
                <div class="bg-accent1 text-white p-3 rounded text-center">默认 (bg-accent1)</div>
                <div class="bg-accent1-100 text-accent1-900 p-3 rounded text-center">100 (bg-accent1-100)</div>
                <div class="bg-accent1-300 text-accent1-900 p-3 rounded text-center">300 (bg-accent1-300)</div>
                <div class="bg-accent1-500 text-white p-3 rounded text-center">500 (bg-accent1-500)</div>
                <div class="bg-accent1-700 text-white p-3 rounded text-center">700 (bg-accent1-700)</div>
                <div class="bg-accent1-900 text-white p-3 rounded text-center">900 (bg-accent1-900)</div>
              </div>
            </div>

            <!-- Accent2 -->
            <div class="space-y-3">
              <h3 class="font-heading text-lg font-semibold text-accent2">Accent2 强调色</h3>
              <div class="space-y-2">
                <div class="bg-accent2 text-white p-3 rounded text-center">默认 (bg-accent2)</div>
                <div class="bg-accent2-100 text-accent2-900 p-3 rounded text-center">100 (bg-accent2-100)</div>
                <div class="bg-accent2-300 text-accent2-900 p-3 rounded text-center">300 (bg-accent2-300)</div>
                <div class="bg-accent2-500 text-white p-3 rounded text-center">500 (bg-accent2-500)</div>
                <div class="bg-accent2-700 text-white p-3 rounded text-center">700 (bg-accent2-700)</div>
                <div class="bg-accent2-900 text-white p-3 rounded text-center">900 (bg-accent2-900)</div>
              </div>
            </div>

            <!-- Accent3 -->
            <div class="space-y-3">
              <h3 class="font-heading text-lg font-semibold text-accent3">Accent3 强调色</h3>
              <div class="space-y-2">
                <div class="bg-accent3 text-white p-3 rounded text-center">默认 (bg-accent3)</div>
                <div class="bg-accent3-100 text-accent3-900 p-3 rounded text-center">100 (bg-accent3-100)</div>
                <div class="bg-accent3-300 text-accent3-900 p-3 rounded text-center">300 (bg-accent3-300)</div>
                <div class="bg-accent3-500 text-white p-3 rounded text-center">500 (bg-accent3-500)</div>
                <div class="bg-accent3-700 text-white p-3 rounded text-center">700 (bg-accent3-700)</div>
                <div class="bg-accent3-900 text-white p-3 rounded text-center">900 (bg-accent3-900)</div>
              </div>
            </div>

            <!-- Accent4 -->
            <div class="space-y-3">
              <h3 class="font-heading text-lg font-semibold text-accent4">Accent4 强调色</h3>
              <div class="space-y-2">
                <div class="bg-accent4 text-white p-3 rounded text-center">默认 (bg-accent4)</div>
                <div class="bg-accent4-100 text-accent4-900 p-3 rounded text-center">100 (bg-accent4-100)</div>
                <div class="bg-accent4-300 text-accent4-900 p-3 rounded text-center">300 (bg-accent4-300)</div>
                <div class="bg-accent4-500 text-white p-3 rounded text-center">500 (bg-accent4-500)</div>
                <div class="bg-accent4-700 text-white p-3 rounded text-center">700 (bg-accent4-700)</div>
                <div class="bg-accent4-900 text-white p-3 rounded text-center">900 (bg-accent4-900)</div>
              </div>
            </div>

            <!-- Accent5 -->
            <div class="space-y-3">
              <h3 class="font-heading text-lg font-semibold text-accent5">Accent5 强调色</h3>
              <div class="space-y-2">
                <div class="bg-accent5 text-white p-3 rounded text-center">默认 (bg-accent5)</div>
                <div class="bg-accent5-100 text-accent5-900 p-3 rounded text-center">100 (bg-accent5-100)</div>
                <div class="bg-accent5-300 text-accent5-900 p-3 rounded text-center">300 (bg-accent5-300)</div>
                <div class="bg-accent5-500 text-white p-3 rounded text-center">500 (bg-accent5-500)</div>
                <div class="bg-accent5-700 text-white p-3 rounded text-center">700 (bg-accent5-700)</div>
                <div class="bg-accent5-900 text-white p-3 rounded text-center">900 (bg-accent5-900)</div>
              </div>
            </div>

            <!-- Accent6 -->
            <div class="space-y-3">
              <h3 class="font-heading text-lg font-semibold text-accent6">Accent6 强调色</h3>
              <div class="space-y-2">
                <div class="bg-accent6 text-white p-3 rounded text-center">默认 (bg-accent6)</div>
                <div class="bg-accent6-100 text-accent6-900 p-3 rounded text-center">100 (bg-accent6-100)</div>
                <div class="bg-accent6-300 text-accent6-900 p-3 rounded text-center">300 (bg-accent6-300)</div>
                <div class="bg-accent6-500 text-white p-3 rounded text-center">500 (bg-accent6-500)</div>
                <div class="bg-accent6-700 text-white p-3 rounded text-center">700 (bg-accent6-700)</div>
                <div class="bg-accent6-900 text-white p-3 rounded text-center">900 (bg-accent6-900)</div>
              </div>
            </div>
          </div>
        </section>

        <!-- 字体系统展示 -->
        <section class="bg-background-subtle border border-border-subtle rounded-lg p-6">
          <div class="flex items-center mb-6">
            <Icon name="star" class="mr-3 size-5 text-primary" />
            <h2 class="font-heading text-2xl font-bold text-primary">字体系统</h2>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
            <!-- 字体家族 -->
            <div>
              <h3 class="font-heading text-lg font-semibold text-primary mb-3">字体家族</h3>
              <div class="space-y-3">
                <div class="bg-background p-4 rounded border">
                  <p class="font-heading text-primary">标题字体 (font-heading)</p>
                  <code class="text-xs text-secondary">font-heading</code>
                </div>
                <div class="bg-background p-4 rounded border">
                  <p class="font-body text-primary">正文字体 (font-body)</p>
                  <code class="text-xs text-secondary">font-body</code>
                </div>
                <div class="bg-background p-4 rounded border">
                  <p class="font-code text-primary">代码字体 (font-code)</p>
                  <code class="text-xs text-secondary">font-code</code>
                </div>
              </div>
            </div>

            <!-- 字体大小 -->
            <div class="md:col-span-2">
              <h3 class="font-heading text-lg font-semibold text-primary mb-3">动态字体大小</h3>
              <div class="space-y-2">
                <div class="flex items-center justify-between bg-background p-3 rounded border">
                  <span class="text-xs text-primary">超小字体</span>
                  <code class="text-xs text-secondary">text-xs</code>
                </div>
                <div class="flex items-center justify-between bg-background p-3 rounded border">
                  <span class="text-sm text-primary">小字体</span>
                  <code class="text-xs text-secondary">text-sm</code>
                </div>
                <div class="flex items-center justify-between bg-background p-3 rounded border">
                  <span class="text-base text-primary">基础字体</span>
                  <code class="text-xs text-secondary">text-base</code>
                </div>
                <div class="flex items-center justify-between bg-background p-3 rounded border">
                  <span class="text-lg text-primary">大字体</span>
                  <code class="text-xs text-secondary">text-lg</code>
                </div>
                <div class="flex items-center justify-between bg-background p-3 rounded border">
                  <span class="text-xl text-primary">超大字体</span>
                  <code class="text-xs text-secondary">text-xl</code>
                </div>
                <div class="flex items-center justify-between bg-background p-3 rounded border">
                  <span class="text-2xl text-primary">2倍大字体</span>
                  <code class="text-xs text-secondary">text-2xl</code>
                </div>
                <div class="flex items-center justify-between bg-background p-3 rounded border">
                  <span class="text-3xl text-primary">3倍大字体</span>
                  <code class="text-xs text-secondary">text-3xl</code>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- 实际应用示例 -->
        <section class="bg-background-subtle border border-border-subtle rounded-lg p-6">
          <div class="flex items-center mb-6">
            <Icon name="star" class="mr-3 size-5 text-primary" />
            <h2 class="font-heading text-2xl font-bold text-primary">实际应用示例</h2>
          </div>

          <!-- 卡片示例 -->
          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <!-- 产品卡片 -->
            <div
              class="bg-background border border-border rounded-lg overflow-hidden hover:border-primary-300 transition-colors">
              <div class="bg-accent1-100 p-4">
                <h3 class="font-heading text-lg text-accent1-800">产品展示</h3>
              </div>
              <div class="p-4">
                <p class="font-body text-secondary text-sm mb-3">
                  使用主题系统构建的产品卡片示例
                </p>
                <div class="flex justify-between items-center">
                  <span class="bg-accent1-200 text-accent1-800 px-2 py-1 rounded text-xs">新品</span>
                  <a href="#" class="text-link hover:text-link-hover text-sm">查看详情</a>
                </div>
              </div>
            </div>

            <!-- 状态卡片 -->
            <div
              class="bg-background border border-border rounded-lg overflow-hidden hover:border-secondary-300 transition-colors">
              <div class="bg-accent2-100 p-4">
                <h3 class="font-heading text-lg text-accent2-800">项目状态</h3>
              </div>
              <div class="p-4">
                <p class="font-body text-secondary text-sm mb-3">
                  展示不同状态的项目进度
                </p>
                <div class="space-y-2">
                  <div class="flex justify-between">
                    <span class="text-sm text-primary">进度</span>
                    <span class="text-sm text-secondary">75%</span>
                  </div>
                  <div class="w-full bg-tertiary-200 rounded-full h-2">
                    <div class="bg-accent2 h-2 rounded-full" style="width: 75%"></div>
                  </div>
                </div>
              </div>
            </div>

            <!-- 数据卡片 -->
            <div
              class="bg-background border border-border rounded-lg overflow-hidden hover:border-tertiary-300 transition-colors">
              <div class="bg-accent3-100 p-4">
                <h3 class="font-heading text-lg text-accent3-800">数据统计</h3>
              </div>
              <div class="p-4">
                <div class="grid grid-cols-2 gap-4 text-center">
                  <div>
                    <div class="text-2xl font-bold text-accent3">1,234</div>
                    <div class="text-xs text-secondary">用户数</div>
                  </div>
                  <div>
                    <div class="text-2xl font-bold text-accent4">567</div>
                    <div class="text-xs text-secondary">订单数</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </template>
  </DefaultContentPage>
</template>

<script setup lang="ts">
import DefaultContentPage from '@/runtime-kit/public/components/page/templates/DefaultContentPage.vue'
import Icon from '@runtime-kit/public/components/primitives/Icon.v1.vue'

defineOptions({
  name: 'ThemeShowcase'
})
</script>
