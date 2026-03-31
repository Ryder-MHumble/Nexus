export type SourceHealthStatus = "healthy" | "warning" | "failing" | "unknown";
export type ExportFormat = "json" | "csv" | "database";

export interface Source {
  id: string;
  name: string;
  dimension: string;
  url?: string;
  is_enabled: boolean;
  crawl_method?: string;
  schedule?: string;
  priority?: number;
  last_crawl_at?: string | null;
  last_success_at?: string | null;
  consecutive_failures?: number;
  source_file?: string | null;
  group?: string | null;
  tags?: string[];
  crawler_class?: string | null;
  dimension_name?: string | null;
  dimension_description?: string | null;
  health_status?: SourceHealthStatus;
  is_enabled_overridden?: boolean;
}

export interface DimensionGroup {
  name: string;
  label: string;
  sources: Source[];
}

export interface CrawlRequest {
  source_ids: string[];
  keyword_filter: string[] | null;
  keyword_blacklist: string[] | null;
  export_format: ExportFormat;
}

export interface CrawlStatus {
  is_running: boolean;
  current_source: string | null;
  completed_sources: string[];
  failed_sources: string[];
  total_items: number;
  progress: number;
}

export interface SourceFacetItem {
  key: string;
  label?: string | null;
  count: number;
}

export interface SourceDimensionFacetItem extends SourceFacetItem {
  enabled_count: number;
}

export interface SourceFacetsResponse {
  dimensions: SourceDimensionFacetItem[];
  groups: SourceFacetItem[];
  tags: SourceFacetItem[];
  crawl_methods: SourceFacetItem[];
  schedules: SourceFacetItem[];
  health_statuses: SourceFacetItem[];
}

export interface SourceCatalogResponse {
  generated_at: string;
  total_sources: number;
  filtered_sources: number;
  page: number;
  page_size: number;
  total_pages: number;
  items: Source[];
  facets?: SourceFacetsResponse | null;
  applied_filters: Record<string, unknown>;
}

export interface CountBucket {
  [key: string]: string | number | null | undefined;
}

export interface InstitutionStatsResponse {
  total_primary_institutions?: number;
  total_secondary_institutions?: number;
  total_universities: number;
  total_departments: number;
  total_scholars: number;
  by_category: CountBucket[];
  by_priority: CountBucket[];
  total_students: number;
  total_mentors: number;
}

export interface ProjectStatsResponse {
  total: number;
  by_category: CountBucket[];
  by_subcategory: CountBucket[];
  total_related_scholars: number;
}

export interface EventStatsResponse {
  total: number;
  by_category: CountBucket[];
  by_series: CountBucket[];
  by_type: CountBucket[];
  by_month: CountBucket[];
  total_related_scholars: number;
}

export interface ScholarStatsBucket {
  name?: string;
  count: number;
  [key: string]: string | number | null | undefined;
}

export interface ScholarStatsResponse {
  total: number;
  academicians: number;
  potential_recruits: number;
  advisor_committee: number;
  adjunct_supervisors: number;
  by_university?: ScholarStatsBucket[];
  by_department?: ScholarStatsBucket[];
  by_position?: ScholarStatsBucket[];
}

export interface ReportDimension {
  id: string;
  name: string;
  description: string;
  status: string;
}

export interface ReportDimensionsResponse {
  dimensions: ReportDimension[];
}

export interface ReportMetadataResponse {
  title: string;
  generated_at: string;
  data_range: string;
  dimension: string;
  total_items: number;
  additional_info: Record<string, unknown>;
}

export interface ReportResponse {
  metadata: ReportMetadataResponse;
  content: string;
  format: string;
}

export interface UniversityLeadershipMember {
  name: string;
  role: string;
  profile_url?: string | null;
  avatar_url?: string | null;
  bio?: string | null;
  intro_lines?: string[];
  source_page_url?: string | null;
  detail_name_text?: string | null;
}

export interface UniversityLeadershipCurrentResponse {
  source_id: string;
  institution_id?: string | null;
  university_name: string;
  source_name?: string | null;
  source_url?: string | null;
  dimension?: string | null;
  group?: string | null;
  crawled_at?: string | null;
  previous_crawled_at?: string | null;
  leader_count: number;
  new_leader_count: number;
  role_counts: Record<string, number>;
  leaders: UniversityLeadershipMember[];
  data_hash?: string | null;
  change_version: number;
  last_changed_at?: string | null;
  updated_at?: string | null;
}

export interface UniversityLeadershipAllResponse {
  total: number;
  items: UniversityLeadershipCurrentResponse[];
}
