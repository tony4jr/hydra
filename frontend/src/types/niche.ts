/**
 * Niche — 시장. Brand 1:N Niche.
 *
 * PR-3a 마이그레이션 결과: brand 마다 default Niche 1:1 백필됨.
 * PR-3b API: /api/admin/niches (CRUD), Brand API 응답에 niches[] 포함.
 */

export type NicheState = 'active' | 'paused' | 'archived'
export type CollectionDepth = 'quick' | 'standard' | 'deep' | 'max'

export interface Niche {
  id: number
  brand_id: number
  name: string
  description: string | null
  market_definition: string | null
  embedding_threshold: number
  trending_vph_threshold: number
  new_video_hours: number
  long_term_score_threshold: number
  collection_depth: CollectionDepth
  keyword_variation_count: number
  preset_per_video_limit: number
  state: NicheState
  created_at?: string
  updated_at?: string
}

export interface NicheOverviewStats {
  video_pool_size: number
  keywords_count: number
  active_campaigns: number
  comments_7d: number
}

export interface NicheActiveCampaign {
  id: number
  name: string | null
  scenario: string
  status: string
  target_count: number | null
  start_date: string | null
  end_date: string | null
}

export interface NicheOverview {
  niche: Niche
  stats: NicheOverviewStats
  active_campaigns: NicheActiveCampaign[]
  recent_alerts: unknown[]
}

// ─── PR-4c: Collection ───────────────────────────────────────────

export type FlowStageName = 'discovered' | 'market_fit' | 'in_pool' | 'comment_posted'

export interface FlowStage {
  stage: FlowStageName
  count: number
  pass_rate: number | null
  is_bottleneck: boolean
}

export interface CollectionFlow {
  window_hours: number
  threshold: number
  stages: FlowStage[]
}

export type KeywordPolling = '5min' | '30min' | 'daily'

export interface KeywordVariation {
  id: number
  text: string
  status: string
}

export interface KeywordWithMetrics {
  id: number
  text: string
  kind: 'positive' | 'negative'
  polling: KeywordPolling
  status: string
  tier: string | null
  variations: KeywordVariation[]
  metrics_7d: {
    discovered: number
    passed_market: number
    pass_rate: number | null
  }
}

export type RecentVideoResult =
  | 'passed'
  | 'rejected_market'
  | 'rejected_hard_block'
  | 'rejected_other'

export interface RecentVideo {
  video_id: string
  title: string | null
  channel: string | null
  view_count: number | null
  url: string
  keyword_matched: string | null
  market_fitness: number | null
  result: RecentVideoResult
  result_reason: string | null
  collected_at: string | null
}

// ─── PR-4d: Messaging ────────────────────────────────────────────

export interface NichePersona {
  id: string
  name: string
  weight: number
  description?: string | null
  age_range?: string | null
  gender?: string | null
}

export interface NicheMessaging {
  niche_id: number
  core_message: string | null
  tone_guide: string | null
  target_audience: string | null
  mention_rules: string | null
  promotional_keywords: string[]
  preset_selection: string[]
  personas: NichePersona[]
}

// ─── PR-4f: Analytics ────────────────────────────────────────────

export interface NicheAnalytics {
  window_days: number
  daily_workload: { date: string; comments: number }[]
  campaign_performance: {
    campaign_id: number
    name: string | null
    status: string
    comments: number
  }[]
  persona_performance: unknown[]
  preset_performance: unknown[]
  hourly_pattern: { hour: number; comments: number }[]
  ranking_summary: { best_campaign_id: number | null; best_comments: number }
}

// ─── PR-4e: Campaigns ────────────────────────────────────────────

export interface NicheCampaign {
  id: number
  name: string | null
  scenario: string
  status: string
  campaign_type: string | null
  comment_mode: string | null
  target_count: number | null
  duration_days: number | null
  start_date: string | null
  end_date: string | null
  created_at: string | null
  completed_at: string | null
}
