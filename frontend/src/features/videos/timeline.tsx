/**
 * /videos/$videoId — 영상 타임라인 (PR-5a).
 */
import { Link, useParams } from '@tanstack/react-router'

import { useVideoTimeline } from '@/hooks/use-videos'
import type { TimelineEvent } from '@/types/video'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { Skeleton } from '@/components/ui/skeleton'

const KIND_LABEL: Record<string, string> = {
  discovered: '발견',
  rejected_filter: '필터 탈락',
  campaign_created: '캠페인 생성',
  comment_posted: '댓글 작성',
  reply_posted: '답글 작성',
}

export default function VideoTimelinePage() {
  const { videoId } = useParams({ from: '/_authenticated/videos/$videoId' })
  const { timeline, loading } = useVideoTimeline(videoId)

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
          <Link to='/videos' className='text-muted-foreground text-[12px] hover:underline'>
            ← 영상 검색
          </Link>
          {loading ? (
            <Skeleton className='h-8 w-72 mt-1' />
          ) : !timeline ? (
            <div className='bg-card border border-border rounded-xl py-16 text-center mt-3'>
              <p className='text-muted-foreground text-[14px]'>영상을 찾지 못했어요</p>
            </div>
          ) : (
            <>
              <div className='mb-5 mt-1'>
                <h1 className='hydra-page-h'>{timeline.video.title || timeline.video.id}</h1>
                <p className='hydra-page-sub'>
                  {timeline.video.channel || '채널 정보 없음'}
                  {timeline.video.view_count !== null && (
                    <> · {timeline.video.view_count.toLocaleString()}회</>
                  )}
                  {timeline.video.niche_name && <> · 시장 {timeline.video.niche_name}</>}
                </p>
                <a
                  href={timeline.video.url}
                  target='_blank'
                  rel='noreferrer'
                  className='text-primary text-[12px] hover:underline'
                >
                  YouTube 열기 ↗
                </a>
              </div>

              <div className='bg-card border border-border rounded-xl p-5'>
                <p className='text-muted-foreground text-[12px] mb-3'>
                  타임라인 ({timeline.events.length} 이벤트)
                </p>
                {timeline.events.length === 0 ? (
                  <p className='text-muted-foreground/60 text-[13px]'>
                    아직 발생한 이벤트가 없어요
                  </p>
                ) : (
                  <ul className='space-y-2'>
                    {timeline.events.map((e, i) => (
                      <TimelineRow key={i} event={e} />
                    ))}
                  </ul>
                )}
              </div>
            </>
          )}
        </div>
      </Main>
    </>
  )
}

function TimelineRow({ event }: { event: TimelineEvent }) {
  const label = KIND_LABEL[event.kind] ?? event.kind
  return (
    <li className='flex items-start gap-3 border-b border-border last:border-0 pb-2'>
      <span className='text-muted-foreground/70 text-[11px] w-32 shrink-0'>
        {event.at ? new Date(event.at).toLocaleString('ko-KR') : '-'}
      </span>
      <div className='min-w-0'>
        <p className='text-foreground text-[13px] font-medium'>
          {label}
          {event.actor && (
            <span className='text-muted-foreground/70 text-[11px] ml-2'>{event.actor}</span>
          )}
        </p>
        {event.actor_detail && (
          <p className='text-muted-foreground/70 text-[11px]'>{event.actor_detail}</p>
        )}
        {event.campaign_name && (
          <p className='text-muted-foreground/70 text-[11px]'>
            campaign: {event.campaign_name}
          </p>
        )}
      </div>
    </li>
  )
}
