// Commex Renewal — shared in-memory store for design verification.
// 작업 흐름(저장/큐로 보내기/즉시 실행/승인/제외) 가 실제로 상태를 바꾸도록.
// localStorage 에 영속화 → 새로고침해도 유지.

import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import {
  QUEUE as INITIAL_QUEUE,
  VIDEOS as INITIAL_VIDEOS,
  AUTO_JOBS as INITIAL_AUTO_JOBS,
  ACTIVITY as INITIAL_ACTIVITY,
  type QueueItem,
  type QueueStatus,
  type Video,
  type VideoStatus,
  type AutoJob,
  type ActivityItem,
} from './_commex-mock'

type QueueDraft = {
  title: string
  brand: string
  niche: string
  // status 미지정 시 큐로 보내기는 'pending', 즉시실행은 'running', 저장은 'draft'
}

type State = {
  queue: QueueItem[]
  videos: Video[]
  autoJobs: AutoJob[]
  activity: ActivityItem[]

  // Queue actions
  saveDraft: (d: QueueDraft) => string
  sendToQueue: (d: QueueDraft) => string
  runNow: (d: QueueDraft) => string
  approveQueue: (id: string) => void
  approveMany: (ids: string[]) => number
  retryQueue: (id: string) => void
  deleteQueue: (id: string) => void

  // Video actions
  excludeVideo: (id: string) => void
  addManualVideos: (input: {
    brand: string
    niche: string
    urls: string[]
  }) => number

  // Auto job actions
  toggleAutoJob: (id: string) => void

  // Activity helper
  pushActivity: (a: Omit<ActivityItem, 'id' | 'time'>) => void

  reset: () => void
}

const newId = (prefix: string) =>
  `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`

export const useCommexStore = create<State>()(
  persist(
    (set, get) => ({
      queue: INITIAL_QUEUE,
      videos: INITIAL_VIDEOS,
      autoJobs: INITIAL_AUTO_JOBS,
      activity: INITIAL_ACTIVITY,

      saveDraft: (d) => {
        const id = newId('q')
        const item: QueueItem = {
          id,
          title: d.title,
          brand: d.brand,
          niche: d.niche,
          createdAt: '방금 전',
          status: 'draft',
          worker: '—',
        }
        set((s) => ({ queue: [item, ...s.queue] }))
        get().pushActivity({
          kind: 'draft',
          title: '초안 저장',
          body: d.title,
        })
        return id
      },

      sendToQueue: (d) => {
        const id = newId('q')
        const item: QueueItem = {
          id,
          title: d.title,
          brand: d.brand,
          niche: d.niche,
          createdAt: '방금 전',
          status: 'pending',
          worker: '—',
        }
        set((s) => ({ queue: [item, ...s.queue] }))
        get().pushActivity({
          kind: 'pending',
          title: '큐 등록 (승인 대기)',
          body: d.title,
        })
        return id
      },

      runNow: (d) => {
        const id = newId('q')
        const item: QueueItem = {
          id,
          title: d.title,
          brand: d.brand,
          niche: d.niche,
          createdAt: '방금 전',
          status: 'running',
          worker: pickAvailableWorker(),
        }
        set((s) => ({ queue: [item, ...s.queue] }))
        get().pushActivity({
          kind: 'auto',
          title: '즉시 실행 시작',
          body: `${d.title} → ${item.worker}`,
        })
        return id
      },

      approveQueue: (id) => {
        const item = get().queue.find((q) => q.id === id)
        if (!item) return
        set((s) => ({
          queue: s.queue.map((q) =>
            q.id === id ? { ...q, status: 'scheduled' as QueueStatus } : q
          ),
        }))
        get().pushActivity({
          kind: 'done',
          title: '승인 완료',
          body: item.title,
        })
      },
      approveMany: (ids) => {
        const targets = ids.filter(
          (id) => get().queue.find((q) => q.id === id)?.status === 'pending'
        )
        if (!targets.length) return 0
        set((s) => ({
          queue: s.queue.map((q) =>
            targets.includes(q.id)
              ? { ...q, status: 'scheduled' as QueueStatus }
              : q
          ),
        }))
        get().pushActivity({
          kind: 'done',
          title: '일괄 승인',
          body: `${targets.length}건 → 예약`,
        })
        return targets.length
      },
      retryQueue: (id) => {
        set((s) => ({
          queue: s.queue.map((q) =>
            q.id === id
              ? { ...q, status: 'pending' as QueueStatus, worker: '—' }
              : q
          ),
        }))
      },
      deleteQueue: (id) => {
        set((s) => ({ queue: s.queue.filter((q) => q.id !== id) }))
      },

      excludeVideo: (id) => {
        set((s) => ({
          videos: s.videos.map((v) =>
            v.id === id ? { ...v, status: '제외' as VideoStatus } : v
          ),
        }))
      },
      addManualVideos: ({ brand, niche, urls }) => {
        if (!urls.length) return 0
        const newOnes: Video[] = urls.map((u, i) => ({
          id: newId(`m${i}`),
          title: '제목 자동 추출 중…',
          brand,
          niche,
          source: '수동 추가',
          date: new Date().toISOString().slice(0, 10),
          lang: 'KO',
          views: '—',
          comments: '—',
          relevance: 0,
          status: '후보' as VideoStatus,
          url: u,
          duration: '—',
        }))
        set((s) => ({ videos: [...newOnes, ...s.videos] }))
        get().pushActivity({
          kind: 'video',
          title: '영상 수동 추가',
          body: `${urls.length}개 / ${brand} · ${niche}`,
        })
        return urls.length
      },

      toggleAutoJob: (id) => {
        set((s) => ({
          autoJobs: s.autoJobs.map((j) =>
            j.id === id ? { ...j, active: !j.active } : j
          ),
        }))
      },

      pushActivity: (a) => {
        const item: ActivityItem = {
          id: newId('a'),
          time: '방금 전',
          ...a,
        }
        set((s) => ({ activity: [item, ...s.activity].slice(0, 30) }))
      },

      reset: () =>
        set({
          queue: INITIAL_QUEUE,
          videos: INITIAL_VIDEOS,
          autoJobs: INITIAL_AUTO_JOBS,
          activity: INITIAL_ACTIVITY,
        }),
    }),
    { name: 'commex-store-v1' }
  )
)

function pickAvailableWorker(): string {
  const ids = ['worker-01', 'worker-02', 'worker-03', 'worker-04', 'worker-05']
  return ids[Math.floor(Math.random() * ids.length)]
}
