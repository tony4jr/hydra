/**
 * Video search + timeline hooks (PR-5a).
 */
import { useEffect, useState } from 'react'

import { fetchApi } from '@/lib/api'
import type { VideoSearchResult, VideoTimeline } from '@/types/video'

export interface VideoSearchParams {
  q?: string
  niche_id?: number
  state?: string
  tier?: string
  sort?: string
  page?: number
  page_size?: number
}

export function useVideoSearch(params: VideoSearchParams) {
  const [result, setResult] = useState<VideoSearchResult | null>(null)
  const [loading, setLoading] = useState(true)

  const qs = new URLSearchParams()
  if (params.q) qs.set('q', params.q)
  if (params.niche_id !== undefined) qs.set('niche_id', String(params.niche_id))
  if (params.state) qs.set('state', params.state)
  if (params.tier) qs.set('tier', params.tier)
  if (params.sort) qs.set('sort', params.sort)
  if (params.page) qs.set('page', String(params.page))
  if (params.page_size) qs.set('page_size', String(params.page_size))
  const search = qs.toString()

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetchApi<VideoSearchResult>(`/videos/api/search?${search}`)
      .then((d) => !cancelled && setResult(d))
      .catch(() => !cancelled && setResult(null))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [search])

  return { result, loading }
}

export function useVideoTimeline(videoId: string) {
  const [timeline, setTimeline] = useState<VideoTimeline | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetchApi<VideoTimeline>(`/videos/api/${videoId}/timeline`)
      .then((d) => !cancelled && setTimeline(d))
      .catch(() => !cancelled && setTimeline(null))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [videoId])

  return { timeline, loading }
}
