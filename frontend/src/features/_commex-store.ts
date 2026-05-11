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
  BRANDS as INITIAL_BRANDS,
  GLOBAL_PRESETS,
  newSlotId,
  type QueueItem,
  type QueueStatus,
  type Video,
  type VideoStatus,
  type AutoJob,
  type ActivityItem,
  type Brand,
  type NichePreset,
  type PresetSlot,
} from './_commex-mock'

export type NicheContext = { brandName: string; nicheName: string } | null

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
  brands: Brand[]
  nicheContext: NicheContext

  // Brand/Niche actions
  addBrand: (input: { name: string; summary: string }) => string
  addNiche: (brandId: string, input: {
    name: string
    desc: string
    keywords: string[]
  }) => string
  updateNicheKeywords: (brandId: string, nicheId: string, keywords: string[]) => void
  updateNichePresets: (brandId: string, nicheId: string, presets: string[]) => void
  deleteBrand: (brandId: string) => void
  deleteNiche: (brandId: string, nicheId: string) => void

  // Niche preset workspace actions
  nichePresets: Record<string, NichePreset[]> // key: nicheId
  forkPresetToNiche: (nicheId: string, globalPresetId: string) => string  // returns new niche preset id
  createNichePreset: (nicheId: string, name: string) => string
  updateNichePreset: (nichePresetId: string, patch: Partial<Pick<NichePreset, 'name' | 'desc'>>) => void
  deleteNichePreset: (nichePresetId: string) => void
  addSlotToNichePreset: (nichePresetId: string, slot: Partial<PresetSlot>) => void
  updateSlot: (nichePresetId: string, slotUid: string, patch: Partial<PresetSlot>) => void
  deleteSlot: (nichePresetId: string, slotUid: string) => void
  duplicateSlot: (nichePresetId: string, slotUid: string) => void
  setNicheContext: (ctx: NicheContext) => void
  clearNicheContext: () => void

  // Queue actions
  saveDraft: (d: QueueDraft) => string
  sendToQueue: (d: QueueDraft) => string
  runNow: (d: QueueDraft) => string
  approveQueue: (id: string) => void
  approveMany: (ids: string[]) => number
  scheduleMany: (ids: string[], schedule: string) => number
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
  upsertAutoJob: (input: {
    id?: string
    brand: string
    niche: string
    active: boolean
    keywords: string[]
    limit: string
    time: string
    nextRun: string
  }) => string
  duplicateAutoJob: (id: string) => string | null

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
      brands: INITIAL_BRANDS,
      nicheContext: null,
      nichePresets: {},

      forkPresetToNiche: (nicheId, globalPresetId) => {
        const g = GLOBAL_PRESETS.find((p) => p.id === globalPresetId)
        if (!g) return ''
        const id = newId('np')
        const np: NichePreset = {
          id,
          niche_id: nicheId,
          name: `${g.name} (니치)`,
          desc: g.desc,
          forked_from: g.id,
          slots: (g.slots ?? []).map((s) => ({ ...s, uid: newSlotId() })),
        }
        set((s) => ({
          nichePresets: {
            ...s.nichePresets,
            [nicheId]: [...(s.nichePresets[nicheId] ?? []), np],
          },
        }))
        get().pushActivity({ kind: 'preset', title: '프리셋 복제', body: np.name })
        return id
      },
      createNichePreset: (nicheId, name) => {
        const id = newId('np')
        const np: NichePreset = {
          id,
          niche_id: nicheId,
          name,
          desc: '',
          slots: [
            {
              uid: newSlotId(),
              account: 'A', target: '메인 댓글', active: true,
              intent: '', tone_anchor: '', legacy_text_template: '',
              length: 'normal', emoji: 'sometimes', ai_freedom: 70,
              mention_brand: false, mention_solution: true,
              style_polite: 'natural', style_pov: 'experience', reduce_repetition: true,
              like_min: 5, like_max: 20,
            },
          ],
        }
        set((s) => ({
          nichePresets: {
            ...s.nichePresets,
            [nicheId]: [...(s.nichePresets[nicheId] ?? []), np],
          },
        }))
        return id
      },
      updateNichePreset: (npId, patch) => {
        set((s) => ({
          nichePresets: Object.fromEntries(
            Object.entries(s.nichePresets).map(([nid, arr]) => [
              nid,
              arr.map((np) => (np.id === npId ? { ...np, ...patch } : np)),
            ])
          ),
        }))
      },
      deleteNichePreset: (npId) => {
        set((s) => ({
          nichePresets: Object.fromEntries(
            Object.entries(s.nichePresets).map(([nid, arr]) => [
              nid,
              arr.filter((np) => np.id !== npId),
            ])
          ),
        }))
      },
      addSlotToNichePreset: (npId, slotPartial) => {
        const slot: PresetSlot = {
          uid: newSlotId(),
          account: 'A', target: '메인 댓글', active: true,
          intent: '', tone_anchor: '', legacy_text_template: '',
          length: 'normal', emoji: 'sometimes', ai_freedom: 70,
          mention_brand: false, mention_solution: true,
          style_polite: 'natural', style_pov: 'experience', reduce_repetition: true,
          like_min: 5, like_max: 20,
          ...slotPartial,
        }
        set((s) => ({
          nichePresets: Object.fromEntries(
            Object.entries(s.nichePresets).map(([nid, arr]) => [
              nid,
              arr.map((np) => (np.id === npId ? { ...np, slots: [...np.slots, slot] } : np)),
            ])
          ),
        }))
      },
      updateSlot: (npId, slotUid, patch) => {
        set((s) => ({
          nichePresets: Object.fromEntries(
            Object.entries(s.nichePresets).map(([nid, arr]) => [
              nid,
              arr.map((np) =>
                np.id !== npId
                  ? np
                  : { ...np, slots: np.slots.map((sl) => (sl.uid === slotUid ? { ...sl, ...patch } : sl)) }
              ),
            ])
          ),
        }))
      },
      deleteSlot: (npId, slotUid) => {
        set((s) => ({
          nichePresets: Object.fromEntries(
            Object.entries(s.nichePresets).map(([nid, arr]) => [
              nid,
              arr.map((np) =>
                np.id !== npId ? np : { ...np, slots: np.slots.filter((sl) => sl.uid !== slotUid) }
              ),
            ])
          ),
        }))
      },
      duplicateSlot: (npId, slotUid) => {
        set((s) => ({
          nichePresets: Object.fromEntries(
            Object.entries(s.nichePresets).map(([nid, arr]) => [
              nid,
              arr.map((np) => {
                if (np.id !== npId) return np
                const idx = np.slots.findIndex((sl) => sl.uid === slotUid)
                if (idx < 0) return np
                const copy: PresetSlot = { ...np.slots[idx], uid: newSlotId() }
                const slots = [...np.slots.slice(0, idx + 1), copy, ...np.slots.slice(idx + 1)]
                return { ...np, slots }
              }),
            ])
          ),
        }))
      },

      addBrand: ({ name, summary }) => {
        const id = newId('b')
        const brand: Brand = {
          id,
          name,
          summary,
          niches: [],
        }
        set((s) => ({ brands: [...s.brands, brand] }))
        get().pushActivity({
          kind: 'preset',
          title: '브랜드 추가',
          body: name,
        })
        return id
      },
      addNiche: (brandId, { name, desc, keywords }) => {
        const id = newId('n')
        set((s) => ({
          brands: s.brands.map((b) =>
            b.id !== brandId
              ? b
              : {
                  ...b,
                  niches: [
                    ...b.niches,
                    {
                      id,
                      name,
                      desc,
                      keywords,
                      presets: ['공감형 메인 댓글'],
                      videos: 0,
                    },
                  ],
                }
          ),
        }))
        const brand = get().brands.find((b) => b.id === brandId)
        get().pushActivity({
          kind: 'preset',
          title: '니치 추가',
          body: `${brand?.name ?? '브랜드'} · ${name}`,
        })
        return id
      },
      updateNicheKeywords: (brandId, nicheId, keywords) => {
        set((s) => ({
          brands: s.brands.map((b) =>
            b.id !== brandId
              ? b
              : {
                  ...b,
                  niches: b.niches.map((n) =>
                    n.id === nicheId ? { ...n, keywords } : n
                  ),
                }
          ),
        }))
      },
      deleteBrand: (brandId) => {
        const target = get().brands.find((b) => b.id === brandId)
        set((s) => ({ brands: s.brands.filter((b) => b.id !== brandId) }))
        if (target) {
          get().pushActivity({
            kind: 'preset',
            title: '브랜드 삭제',
            body: target.name,
          })
        }
      },
      deleteNiche: (brandId, nicheId) => {
        const brand = get().brands.find((b) => b.id === brandId)
        const niche = brand?.niches.find((n) => n.id === nicheId)
        set((s) => ({
          brands: s.brands.map((b) =>
            b.id !== brandId
              ? b
              : { ...b, niches: b.niches.filter((n) => n.id !== nicheId) }
          ),
        }))
        if (brand && niche) {
          get().pushActivity({
            kind: 'preset',
            title: '니치 삭제',
            body: `${brand.name} · ${niche.name}`,
          })
        }
      },
      updateNichePresets: (brandId, nicheId, presets) => {
        set((s) => ({
          brands: s.brands.map((b) =>
            b.id !== brandId
              ? b
              : {
                  ...b,
                  niches: b.niches.map((n) =>
                    n.id === nicheId ? { ...n, presets } : n
                  ),
                }
          ),
        }))
      },
      setNicheContext: (ctx) => set({ nicheContext: ctx }),
      clearNicheContext: () => set({ nicheContext: null }),

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
      scheduleMany: (ids, schedule) => {
        const targets = ids.filter((id) => {
          const status = get().queue.find((q) => q.id === id)?.status
          return status === 'draft' || status === 'pending' || status === 'scheduled'
        })
        if (!targets.length) return 0
        set((s) => ({
          queue: s.queue.map((q) =>
            targets.includes(q.id)
              ? {
                  ...q,
                  status: 'scheduled' as QueueStatus,
                  worker: q.worker === '—' ? pickAvailableWorker() : q.worker,
                  createdAt: schedule,
                }
              : q
          ),
        }))
        get().pushActivity({
          kind: 'pending',
          title: '예약 변경',
          body: `${targets.length}건 → ${schedule}`,
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
      upsertAutoJob: (input) => {
        const id = input.id ?? newId('aj')
        const job: AutoJob = {
          id,
          brand: input.brand,
          niche: input.niche,
          active: input.active,
          nextRun: input.nextRun,
          lastRun: input.id
            ? (get().autoJobs.find((j) => j.id === input.id)?.lastRun ?? '—')
            : '—',
          keywords: input.keywords,
          limit: input.limit,
          time: input.time,
        }
        set((s) => ({
          autoJobs: input.id
            ? s.autoJobs.map((j) => (j.id === input.id ? job : j))
            : [job, ...s.autoJobs],
        }))
        get().pushActivity({
          kind: 'auto',
          title: input.id ? '자동 작업 수정' : '자동 작업 생성',
          body: `${job.brand} · ${job.niche}`,
        })
        return id
      },
      duplicateAutoJob: (id) => {
        const src = get().autoJobs.find((j) => j.id === id)
        if (!src) return null
        const nextId = newId('aj')
        const clone: AutoJob = {
          ...src,
          id: nextId,
          active: false,
          nextRun: '내일 09:00',
          lastRun: '—',
          limit: `${src.limit} 복제`,
        }
        set((s) => ({ autoJobs: [clone, ...s.autoJobs] }))
        get().pushActivity({
          kind: 'auto',
          title: '자동 작업 복제',
          body: `${clone.brand} · ${clone.niche}`,
        })
        return nextId
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
          brands: INITIAL_BRANDS,
          nicheContext: null,
        }),
    }),
    {
      name: 'commex-store-v2',
      version: 2,
    }
  )
)

function pickAvailableWorker(): string {
  const ids = ['worker-01', 'worker-02', 'worker-03', 'worker-04', 'worker-05']
  return ids[Math.floor(Math.random() * ids.length)]
}
