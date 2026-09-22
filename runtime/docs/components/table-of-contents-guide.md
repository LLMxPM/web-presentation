# 目录能力使用说明

Runtime Kit 不再把 `TableOfContents` 作为推荐公开 UI 组件。目录的视觉结构、列数、序号格式、点线、字号和交互样式应由 Backend/Agent 在页面源码中生成；Runtime Kit 只通过 `useRouteCatalog` 提供当前项目的路由目录数据。

## 1. 使用场景

适合使用 `useRouteCatalog` 的场景：

- 根据当前 Runtime 路由配置生成目录页。
- 在自定义导航中按页码排序展示页面。
- 根据路径、名称或页码查询页面信息。

不适合交给 Runtime Kit 的内容：

- 目录 UI 组件。
- 双列/三列布局。
- 序号圆点、虚线、章节样式。
- 目录页整体模板。

## 2. 基础用法

```vue
<script setup lang="ts">
import DefaultContainer from '@runtime-kit/public/components/page/layout/DefaultContainer.v1.vue'
import { useRouteCatalog } from '@runtime-kit/public/composables/page/useRouteCatalog.v1'

const { catalogItems } = useRouteCatalog()
</script>

<template>
  <DefaultContainer>
    <main class="relative h-full p-20">
      <h1 class="mb-12 text-5xl font-bold">目录</h1>
      <ol class="space-y-5">
        <li
          v-for="(item, index) in catalogItems"
          :key="item.id"
          class="flex items-baseline gap-6"
        >
          <span class="w-12 text-right font-bold">{{ index + 1 }}</span>
          <span class="flex-1">{{ item.title }}</span>
          <span>{{ item.pageNumber }}</span>
        </li>
      </ol>
    </main>
  </DefaultContainer>
</template>
```

## 3. 可用数据和函数

`useRouteCatalog()` 返回：

| 字段 | 说明 |
| --- | --- |
| `visibleRoutes` | 未隐藏路由信息 |
| `routesByOrder` | 按 order 排序的路由 |
| `routesByPageNumber` | 按 pageNumber 排序的路由 |
| `catalogItems` | 适合目录消费的简化条目 |
| `minPageNumber` | 最小页码 |
| `maxPageNumber` | 最大页码 |
| `getPageNumberByName` | 按名称查询页码 |
| `getPageNumberByPath` | 按路径查询页码 |
| `getRouteInfoByName` | 按名称查询路由信息 |
| `getRouteInfoByPageNumber` | 按页码查询路由信息 |
| `getRouteInfoByPath` | 按路径查询路由信息 |

`catalogItems` 的条目结构：

```ts
interface RuntimeKitRouteCatalogItem {
  id: string
  title: string
  path: string
  order: number
  pageNumber?: number
  parentPath?: string
}
```

## 4. 可点击目录

如果目录需要点击跳转，可以配合 `vue-router` 使用。跳转按钮和样式仍由页面源码生成。

```vue
<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useRouteCatalog } from '@runtime-kit/public/composables/page/useRouteCatalog.v1'

const router = useRouter()
const { catalogItems } = useRouteCatalog()

function go(path: string) {
  router.push(path)
}
</script>

<template>
  <button
    v-for="item in catalogItems"
    :key="item.id"
    type="button"
    @click="go(item.path)"
  >
    {{ item.title }}
  </button>
</template>
```

## 5. 约束

- 目录数据依赖 Runtime 路由配置。
- `useRouteCatalog` 只提供数据，不负责目录 UI。
- Backend/Agent 不应为了隔离组件预览伪造业务路由。
- 新页面不应再引用旧路径 `@runtime-kit/components/...`。
- 页面源码不应引用 `@runtime-kit/internal/...`。
- 页面源码不应引用未带 `.vN` 的 `@runtime-kit/public/...` 路径。
