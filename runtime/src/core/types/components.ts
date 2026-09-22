/**
 * 组件相关类型定义
 */

// 基础组件Props接口
export interface BaseComponentProps {
  className?: string
  id?: string
}

// Title组件Props
export interface TitleProps extends BaseComponentProps {
  level: 1 | 2 | 3 | 4 | 5 | 6
}

// Card组件Props
export interface CardProps extends BaseComponentProps {
  title?: string
  bordered?: boolean
}

// Table组件相关类型
export interface TableColumn<T = Record<string, unknown>> {
  key: keyof T
  title: string
  width?: string
  sortable?: boolean
  render?: (value: T[keyof T], record: T) => unknown
}

export interface TableProps<T = Record<string, unknown>> extends BaseComponentProps {
  data: T[]
  columns: TableColumn<T>[]
}

// ComparisonTable组件类型
export interface ComparisonItem {
  feature: string
  options: {
    name: string
    value: unknown
    highlight?: boolean
  }[]
}

export interface ComparisonTableProps extends BaseComponentProps {
  data: ComparisonItem[]
}

// Button组件Props
export interface ButtonProps extends BaseComponentProps {
  type?: 'primary' | 'secondary' | 'danger' | 'success' | 'warning' | 'ghost' | 'link'
  size?: 'default' | 'small' | 'medium' | 'large'
  disabled?: boolean
  loading?: boolean
}

// ComparisonTable组件额外类型
export interface ComparisonOption {
  name: string
  description?: string
  badge?: string
  highlight?: boolean
  popular?: boolean
}

export interface ComparisonData {
  feature: string
  [key: string]: unknown
}

// Layout组件类型
export interface TabItem {
  key: string
  label: string
  content?: string
  disabled?: boolean
}

export interface StepItem {
  key?: string | number
  title: string
  description?: string
  icon?: unknown
  status?: 'pending' | 'active' | 'completed' | 'error'
  disabled?: boolean
}

export interface TimelineItem {
  key?: string | number
  title?: string
  description?: string
  content?: string
  timestamp?: string | Date
  icon?: unknown
  dot?: string
  type?: 'default' | 'primary' | 'success' | 'warning' | 'danger' | 'info'
  tags?: string[]
}

export interface AccordionItem {
  key?: string
  title: string
  content: string
  disabled?: boolean
  icon?: string
}



// API响应类型
export interface ApiResponse<T> {
  code: number
  message: string
  data: T
}



