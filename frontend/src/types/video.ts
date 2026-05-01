/**
 * Video search + timeline types (PR-5a).
 */

export interface VideoSummary {
  id: string
  title: string | null
  channel: string | null
  view_count: number | null
  comment_count: number | null
  published_at: string | null
  discovered_at: string | null
  state: string | null
  tier: string | null
  market_fitness: number | null
  niche_id: number | null
  url: string
  is_short: boolean | null
}

export interface VideoSearchResult {
  total: number
  page: number
  page_size: number
  items: VideoSummary[]
}

export interface TimelineEvent {
  at: string | null
  kind: string
  actor?: 'system' | 'operator' | 'worker' | null
  actor_detail?: string | null
  campaign_id?: number | null
  campaign_name?: string | null
  metadata?: Record<string, unknown>
}

export interface VideoTimelineDetail {
  id: string
  title: string | null
  channel: string | null
  url: string
  view_count: number | null
  comment_count: number | null
  state: string | null
  tier: string | null
  market_fitness: number | null
  niche_id: number | null
  niche_name: string | null
}

export interface VideoTimeline {
  video: VideoTimelineDetail
  events: TimelineEvent[]
  upcoming: TimelineEvent[]
}
