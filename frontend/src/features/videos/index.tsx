/**
 * /videos — 영상 검색 + 필터 (PR-5a).
 */
import { useState } from 'react'
import { Link } from '@tanstack/react-router'

import { useVideoSearch } from '@/hooks/use-videos'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { Skeleton } from '@/components/ui/skeleton'

const STATE_OPTIONS = ['', 'pending', 'active', 'paused', 'completed', 'blacklisted']
const TIER_OPTIONS = ['', 'L1', 'L2', 'L3', 'L4']
const SORT_OPTIONS = [
  ['recent', '최근'],
  ['views', '조회수'],
  ['fitness', '적합도'],
  ['comment_count', '댓글수'],
] as const

export default function VideosPage() {
  const [q, setQ] = useState('')
  const [state, setState] = useState('')
  const [tier, setTier] = useState('')
  const [sort, setSort] = useState<string>('recent')
  const [page, setPage] = useState(1)
  const { result, loading } = useVideoSearch({
    q: q || undefined,
    state: state || undefined,
    tier: tier || undefined,
    sort,
    page,
    page_size: 50,
  })

  return (
    <>
      <Header fixed>
        <div className='ml-auto flex items-center space-x-4'>
          <ThemeSwitch />
          <ProfileDropdown />
        </div>
      </Header>
      <Main>
        <div>
          <div className='mb-5'>
            <h1 className='hydra-page-h'>영상</h1>
            <p className='hydra-page-sub'>전체 영상 검색·추적</p>
          </div>

          <div className='flex flex-wrap gap-2 mb-4'>
            <input
              value={q}
              onChange={(e) => {
                setQ(e.target.value)
                setPage(1)
              }}
              placeholder='제목·채널 검색...'
              className='flex-1 min-w-[200px] bg-background border border-border rounded-md text-[13px] px-2 py-1.5'
            />
            <select
              value={state}
              onChange={(e) => {
                setState(e.target.value)
                setPage(1)
              }}
              className='bg-background border border-border rounded-md text-[13px] px-2 py-1.5'
            >
              {STATE_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {s || '상태 전체'}
                </option>
              ))}
            </select>
            <select
              value={tier}
              onChange={(e) => {
                setTier(e.target.value)
                setPage(1)
              }}
              className='bg-background border border-border rounded-md text-[13px] px-2 py-1.5'
            >
              {TIER_OPTIONS.map((t) => (
                <option key={t} value={t}>
                  {t || '티어 전체'}
                </option>
              ))}
            </select>
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value)}
              className='bg-background border border-border rounded-md text-[13px] px-2 py-1.5'
            >
              {SORT_OPTIONS.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </div>

          {loading ? (
            <Skeleton className='h-64 rounded-xl' />
          ) : !result ? (
            <div className='bg-card border border-border rounded-xl py-16 text-center'>
              <p className='text-muted-foreground text-[13px]'>검색에 실패했어요</p>
            </div>
          ) : (
            <div className='bg-card border border-border rounded-xl overflow-hidden'>
              <div className='px-4 py-2 border-b border-border text-muted-foreground text-[12px]'>
                {result.total}개 영상
              </div>
              <ul className='divide-y divide-border'>
                {result.items.map((v) => (
                  <li key={v.id}>
                    <Link
                      to='/videos/$videoId'
                      params={{ videoId: v.id }}
                      className='block px-4 py-3 hover:bg-muted/30'
                    >
                      <div className='flex items-center justify-between gap-3'>
                        <div className='min-w-0'>
                          <p className='text-foreground text-[14px] font-medium truncate'>
                            {v.title || v.id}
                          </p>
                          <p className='text-muted-foreground/70 text-[11px] truncate'>
                            {v.channel || '채널 정보 없음'}
                            {v.view_count !== null && (
                              <> · {v.view_count.toLocaleString()}회</>
                            )}
                            {v.tier && <> · {v.tier}</>}
                            {v.market_fitness !== null && (
                              <> · 적합도 {v.market_fitness.toFixed(2)}</>
                            )}
                          </p>
                        </div>
                        <span className={`hydra-tag ${stateTone(v.state)}`}>
                          {v.state || 'unknown'}
                        </span>
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
              <div className='flex items-center justify-between px-4 py-2 border-t border-border'>
                <span className='text-muted-foreground/70 text-[12px]'>
                  {result.page} / {Math.max(1, Math.ceil(result.total / result.page_size))}
                </span>
                <div className='flex gap-2'>
                  <button
                    disabled={page <= 1}
                    onClick={() => setPage(page - 1)}
                    className='text-[12px] px-2 py-1 border border-border rounded disabled:opacity-40'
                  >
                    이전
                  </button>
                  <button
                    disabled={page >= Math.ceil(result.total / result.page_size)}
                    onClick={() => setPage(page + 1)}
                    className='text-[12px] px-2 py-1 border border-border rounded disabled:opacity-40'
                  >
                    다음
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </Main>
    </>
  )
}

function stateTone(state: string | null): string {
  if (state === 'active') return 'hydra-tag-primary'
  if (state === 'blacklisted') return 'hydra-tag-muted'
  return 'hydra-tag-muted'
}
