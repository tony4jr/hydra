import { Link } from '@tanstack/react-router'

import { useQueue } from '@/hooks/use-feed'
import { useActiveBrand } from '@/lib/active-brand'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { Skeleton } from '@/components/ui/skeleton'

export default function QueuePage() {
  const { activeBrand } = useActiveBrand()
  const { data, loading } = useQueue(activeBrand?.id ?? null, 24)

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
            <h1 className='hydra-page-h'>예정</h1>
            <p className='hydra-page-sub'>다음 24시간 안에 일어날 작업</p>
          </div>

          {loading ? (
            <Skeleton className='h-64 rounded-xl' />
          ) : !data || data.total === 0 ? (
            <div className='bg-card border border-border rounded-xl py-16 text-center'>
              <p className='text-muted-foreground text-[14px]'>예정된 작업이 없어요</p>
            </div>
          ) : (
            <ul className='space-y-2'>
              {data.items.map((q, i) => (
                <li key={i} className='bg-card border border-border rounded-xl p-4'>
                  <div className='flex items-center justify-between gap-2 mb-1'>
                    <span className='text-muted-foreground/70 text-[11px]'>
                      {q.at ? new Date(q.at).toLocaleString('ko-KR') : '-'}
                    </span>
                    <span className='hydra-tag hydra-tag-muted'>{q.kind}</span>
                  </div>
                  {q.video_id ? (
                    <Link
                      to='/videos/$videoId'
                      params={{ videoId: q.video_id }}
                      className='text-foreground text-[13px] hover:underline'
                    >
                      {q.detail}
                    </Link>
                  ) : (
                    <p className='text-foreground text-[13px]'>{q.detail}</p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </Main>
    </>
  )
}
