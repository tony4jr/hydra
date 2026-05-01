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
