# previewSchema 契约

previewSchema 用于描述工作空间组件的典型预览输入，让 Runtime 可以渲染组件不同状态，并让 AI 理解组件参数边界。

## 职责

- 组件作者提供典型参数组合。
- Backend 校验 previewSchema 中的可导入能力。
- Runtime 根据 schema 渲染组件预览。
- Editor 展示预览结果和错误信息。

## 约束

previewSchema 不能引用未进入 Runtime Kit manifest 的能力，也不能依赖 Runtime shell 内部实现。需要资源、字体或主题时，应通过平台公开对象引用。

## 测试

调整 previewSchema 结构、校验规则或 Runtime 渲染方式时，应补充 Backend 契约测试、Runtime 组件预览测试和必要的 Editor 展示测试。
