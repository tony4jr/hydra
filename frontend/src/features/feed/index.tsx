import { useState } from 'react'
import { Link } from '@tanstack/react-router'

import { useFeed } from '@/hooks/use-feed'
import { useActiveBrand } from '@/lib/active-brand'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { Skeleton } from '@/components/ui/skeleton'

const WINDOWS: Array<[string, string]> = [
  ['1h', '최근 1시간'],
  ['24h', '24시간'],
  ['week', '이번 주'],
  ['month', '이번 달'],
]

export default function FeedPage() {
  const [windowKey, setWindowKey] = useState('24h')
  const { activeBrand } = useActiveBrand()
  const { data, loading } = useFeed(windowKey, activeBrand?.id ?? null)

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
            <h1 className='hydra-page-h'>피드</h1>
            <p className='hydra-page-sub'>지금 무슨 일이 일어나고 있는지 시간순으로</p>
          </div>

          <div className='flex flex-wrap gap-2 mb-4'>
            {WINDOWS.map(([key, label]) => (
              <button
                key={key}
                onClick={() => setWindowKey(key)}
                className={
                  'px-3 py-1.5 text-[13px] rounded-md border transition-colors ' +
                  (windowKey === key
                    ? 'bg-primary text-primary-foreground border-primary'
                    : 'bg-background border-border hover:bg-muted/60')
                }
              >
                {label}
              </button>
            ))}
          </div>

          {loading ? (
            <Skeleton className='h-64 rounded-xl' />
          ) : !data || data.events.length === 0 ? (
            <div className='bg-card border border-border rounded-xl py-16 text-center'>
              <p className='text-muted-foreground text-[14px]'>
                {windowKey} 기간 안에 발생한 이벤트가 없어요
              </p>
            </div>
          ) : (
            <ul className='space-y-2'>
              {data.events.map((e, i) => (
                <FeedRow key={i} event={e} />
              ))}
            </ul>
          )}
        </div>
      </Main>
    </>
  )
}

function FeedRow({ event }: { event: import('@/types/feed').FeedEvent }) {
  const time = event.at ? new Date(event.at).toLocaleString('ko-KR') : '-'
  const meta = event.metadata as Record<string, any>

  return (
    <li className='bg-card border border-border rounded-xl p-4'>
      <div className='flex items-center justify-between gap-2 mb-1'>
        <span className='text-muted-foreground/70 text-[11px]'>{time}</span>
        <span className='hydra-tag hydra-tag-muted'>{KIND_LABEL[event.kind] ?? event.kind}</span>
      </div>
      {event.kind === 'comment_posted' && (
        <div>
          <p className='text-foreground text-[13px]'>
            {event.video_id ? (
              <Link
                to='/videos/$videoId'
                params={{ videoId: event.video_id }}
                className='hover:underline'
              >
                영상 보기 ↗
              </Link>
            ) : (
              '댓글 작성'
            )}
          </p>
          {meta.content && (
            <p className='text-muted-foreground text-[12px] mt-1'>"{meta.content}"</p>
          )}
          <p className='text-muted-foreground/70 text-[11px] mt-1'>
            {event.actor} · {meta.action_type} {meta.is_promo ? '· 프로모' : ''}
          </p>
        </div>
      )}
      {event.kind === 'video_discovered' && (
        <div>
          <p className='text-foreground text-[13px]'>
            {event.video_id ? (
              <Link
                to='/videos/$videoId'
                params={{ videoId: event.video_id }}
                className='hover:underline'
              >
                {meta.title || event.video_id}
              </Link>
            ) : (
              meta.title
            )}
          </p>
          <p className='text-muted-foreground/70 text-[11px] mt-1'>
            {meta.channel}
            {meta.view_count !== null && <> · {Number(meta.view_count).toLocaleString()}회</>}
          </p>
        </div>
      )}
      {event.kind === 'campaign_event' && (
        <div>
          <p className='text-foreground text-[13px]'>{meta.name || `캠페인 #${event.campaign_id}`}</p>
          <p className='text-muted-foreground/70 text-[11px] mt-1'>
            {meta.scenario} · {meta.status}
          </p>
        </div>
      )}
    </li>
  )
}

const KIND_LABEL: Record<string, string> = {
  comment_posted: '댓글',
  video_discovered: '영상 발견',
  campaign_event: '캠페인',
}
