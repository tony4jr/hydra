export interface FeedEvent {
  at: string | null
  kind: 'comment_posted' | 'video_discovered' | 'campaign_event'
  actor: string | null
  video_id: string | null
  niche_id: number | null
  campaign_id?: number | null
  metadata: Record<string, unknown>
}

export interface FeedResponse {
  window: string
  events: FeedEvent[]
}

export interface AlertItem {
  id: string
  kind: string
  severity: 'info' | 'warn' | 'critical'
  title: string
  detail: string
  related_link: string | null
  created_at: string | null
}

export interface AlertsResponse {
  total: number
  alerts: AlertItem[]
}

export interface QueueItem {
  at: string | null
  kind: string
  video_id: string | null
  niche_id: number | null
  detail: string
}

export interface QueueResponse {
  window_hours: number
  total: number
  items: QueueItem[]
}
