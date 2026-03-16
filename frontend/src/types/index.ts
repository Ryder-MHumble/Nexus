export interface Source {
  id: string
  name: string
  dimension: string
  url?: string
  is_enabled: boolean
  crawl_method?: string
  schedule?: string
  last_crawl_at?: string | null
  failure_count?: number
}

export interface DimensionGroup {
  name: string
  label: string
  sources: Source[]
}

export type ExportFormat = 'json' | 'csv' | 'database'

export interface CrawlRequest {
  source_ids: string[]
  keyword_filter: string[] | null
  keyword_blacklist: string[] | null
  export_format: ExportFormat
}

export interface CrawlStatus {
  is_running: boolean
  current_source: string | null
  completed_sources: string[]
  failed_sources: string[]
  total_items: number
  progress: number
}
