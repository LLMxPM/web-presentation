# 图标系统使用指南

当前 Runtime 只支持静态图标资源。

## 基本规则

- `Icon` 组件的 `name` 必须等于图标资源的逻辑名 `asset.name`。
- 预览模式下，Backend 会根据当前预览对象实际用到的 `Icon name` 动态生成最小 `static_icons` 配置，并把 `src` 作为同一个逻辑名下发给 Runtime。
- 如果源码里出现无法静态解析的 `:name`，或引用了不存在的图标资源，预览会直接报错。
- 图标默认尺寸等于当前页面基础字号；局部尺寸使用 `size-*` 或 `h-* w-*` Tailwind 类控制。
- 图标默认描边宽度由 `app.config.yaml` 的 `app.page.iconDefaultStrokeWidth` 控制。

## icons.config.yaml

本地 Runtime 演示环境仍保留 `public/config/icons.config.yaml`，但结构只允许：

```yaml
static_icons:
  - name: slider
    src: img/icon/slider.svg
  - name: home
    src: img/icon/home.svg
```

字段说明：

- `name`：运行时引用名，也是 `Icon` 组件使用的资源逻辑名。
- `src`：本地 Runtime 下可以写相对路径；在预览模式下，Backend 会把它下发为同名逻辑标识，再由 manifest assets 解析到真实文件。

## 项目页面默认值

图标默认样式不写在 `icons.config.yaml`，也不再属于主题，而是跟页面尺寸一起写到项目页面配置里：

```yaml
app:
  page:
    width: 1920
    height: 1080
    baseFontSize: 16px
    iconDefaultStrokeWidth: 2
```

Runtime 仍兼容旧 `themes.config.yaml` 中的 `themes.<key>.icon.*` 作为 fallback，用于渲染历史 preview artifact 或旧静态配置；新 Backend 与 Editor 不再生成或编辑这些字段。`baseFontSize` 只影响页面内容与页面内图标的默认尺寸，并作为 Tailwind 默认 16px 基准替换值影响语义字号和间距倍率，不影响 Runtime shell UI。

## 使用示例

```vue
<template>
  <Icon name="home" />
  <Icon name="brand-home" class="size-6" color="#2563eb" />
</template>
```

## 相关文件

- `public/config/icons.config.yaml`
- `public/config/themes.config.yaml`
- `src/core/utils/icon-registry.ts`
- `src/core/composables/useIcon.ts`
- `src/runtime-kit/components/primitives/Icon.vue`
