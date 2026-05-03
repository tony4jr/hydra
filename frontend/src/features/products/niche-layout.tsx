/**
 * /brands/$brandId/niches/$nicheId — 시장 5탭 layout.
 *
 * PR-4a 골격. Outlet 으로 5탭 콘텐츠 렌더 (overview/collection/messaging/campaigns/analytics).
 * 각 탭 콘텐츠는 placeholder, 후속 sub-PR (4b~f) 에서 채움.
 */
import { useEffect, useState } from 'react'
import { Link, Outlet, useLocation, useParams } from '@tanstack/react-router'

import { useSyncActiveBrand } from '@/hooks/use-sync-active-brand'
import { fetchApi } from '@/lib/api'
import { labels } from '@/lib/i18n-terms'
import type { Niche } from '@/types/niche'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { Skeleton } from '@/components/ui/skeleton'

interface TabDef {
  key: 'overview' | 'collection' | 'messaging' | 'campaigns' | 'analytics'
  label: string
  suffix: string
}

const TABS: TabDef[] = [
  { key: 'overview', label: labels.tabOverview, suffix: '' },
  { key: 'collection', label: labels.tabCollection, suffix: '/collection' },
  { key: 'messaging', label: labels.tabMessaging, suffix: '/messaging' },
  { key: 'campaigns', label: labels.tabCampaigns, suffix: '/campaigns' },
  { key: 'analytics', label: labels.tabAnalytics, suffix: '/analytics' },
]

export default function NicheLayout() {
  const { brandId, nicheId } = useParams({
    from: '/_authenticated/brands/$brandId/niches/$nicheId',
  })
  useSyncActiveBrand(Number(brandId))
  const location = useLocation()
  const base = `/brands/${brandId}/niches/${nicheId}`
  const activeSuffix = location.pathname.replace(base, '') || ''

  const [niche, setNiche] = useState<Niche | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchApi<Niche>(`/api/admin/niches/${nicheId}`)
      .then(setNiche)
      .catch(() => setNiche(null))
      .finally(() => setLoading(false))
  }, [nicheId])

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
            <Link
              to='/brands/$brandId'
              params={{ brandId }}
              className='text-muted-foreground text-[12px] hover:underline'
            >
              ← {labels.niche} 목록
            </Link>
            {loading ? (
              <Skeleton className='h-8 w-48 mt-1' />
            ) : (
              <>
                <h1 className='hydra-page-h mt-1'>{niche?.name ?? `${labels.niche} #${nicheId}`}</h1>
                <p className='hydra-page-sub'>
                  {niche?.market_definition || '시장 정의가 비어있어요'}
                </p>
              </>
            )}
          </div>

          <div className='border-b border-border mb-5 -mx-1 overflow-x-auto'>
            <nav className='flex gap-1 px-1'>
              {TABS.map((tab) => {
                const active = activeSuffix === tab.suffix
                return (
                  <Link
                    key={tab.key}
                    to={`${base}${tab.suffix}` as string}
                    className={
                      'px-3 py-2 text-[14px] font-medium border-b-2 -mb-[1px] transition-colors ' +
                      (active
                        ? 'border-primary text-foreground'
                        : 'border-transparent text-muted-foreground hover:text-foreground')
                    }
                  >
                    {tab.label}
                  </Link>
                )
              })}
            </nav>
          </div>

          <Outlet />
        </div>
      </Main>
    </>
  )
}
