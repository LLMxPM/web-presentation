/**
 * 文件用途：声明 Runtime 壳层内使用的非代码静态资源模块类型，供 TypeScript 和 vue-tsc 正确识别。
 */

declare module '*.drawio' {
  const src: string
  export default src
}
