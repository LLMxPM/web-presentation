/** 文件功能：由 model_view_options.v1.json 生成的共享类型，勿手改；运行 pnpm run codegen:model-view-types。 */

export type ModelViewOptions = {
  "name": string
  "sceneIndex"?: number
  "cameraIndex"?: number
  "cameraPosition"?: ModelViewVector3
  "cameraTarget"?: ModelViewVector3
  "cameraFov"?: number
  "background"?: string
  "lighting"?: "auto" | "source"
  "interactive"?: boolean
  "fallback"?: string
  "class"?: string
}

export type ModelViewVector3 = [number, number, number]
