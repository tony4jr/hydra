import { useAlerts } from '@/hooks/use-feed'
import { useActiveBrand } from '@/lib/active-brand'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { Skeleton } from '@/components/ui/skeleton'

export default function AlertsPage() {
  const { activeBrand } = useActiveBrand()
  const { data, loading } = useAlerts(activeBrand?.id ?? null)

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
            <h1 className='hydra-page-h'>문제</h1>
            <p className='hydra-page-sub'>당장 손 봐야 할 빨간불 모음</p>
          </div>

          {loading ? (
            <Skeleton className='h-64 rounded-xl' />
          ) : !data || data.total === 0 ? (
            <div className='bg-card border border-border rounded-xl py-16 text-center'>
              <p className='text-muted-foreground text-[14px]'>지금은 별일 없어요 ☕</p>
            </div>
          ) : (
            <ul className='space-y-2'>
              {data.alerts.map((a) => {
                const tone =
                  a.severity === 'critical'
                    ? 'border-rose-400/60'
                    : a.severity === 'warn'
                    ? 'border-amber-400/60'
                    : 'border-border'
                return (
                  <li
                    key={a.id}
                    className={`bg-card border ${tone} rounded-xl p-4`}
                  >
                    <div className='flex items-center justify-between mb-1'>
                      <span className='text-foreground text-[14px] font-medium'>{a.title}</span>
                      <span className='hydra-tag hydra-tag-muted'>{a.severity}</span>
                    </div>
                    <p className='text-muted-foreground text-[12px]'>{a.detail}</p>
                    {a.related_link && (
                      <a
                        href={a.related_link}
                        className='text-primary text-[12px] hover:underline mt-1 inline-block'
                      >
                        이동 →
                      </a>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </Main>
    </>
  )
}
