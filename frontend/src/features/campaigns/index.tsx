import { useEffect, useState } from 'react'
import { Plus, Zap } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { fetchApi } from '@/lib/api'

interface Campaign {
  id: number
  video_title: string
  brand_name: string
  scenario: string
  campaign_type: string
  status: string
  created_at: string
}

interface CampaignListResponse {
  items: Campaign[]
  total: number
}

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([])

  useEffect(() => {
    fetchApi<CampaignListResponse>('/campaigns/api/list')
      .then((data) => setCampaigns(data.items || []))
      .catch(() => {})
  }, [])

  const statusColor = (s: string) => {
    switch (s) {
      case 'in_progress':
        return 'default' as const
      case 'completed':
        return 'secondary' as const
      case 'planning':
        return 'outline' as const
      case 'failed':
        return 'destructive' as const
      default:
        return 'secondary' as const
    }
  }

  const campaignTable = (items: Campaign[]) => (
    <Card>
      <CardContent className='p-0'>
        <div className='overflow-auto'>
          <table className='w-full text-sm'>
            <thead>
              <tr className='border-b bg-muted/50'>
                <th className='p-3 text-left font-medium'>영상</th>
                <th className='p-3 text-left font-medium'>브랜드</th>
                <th className='p-3 text-center font-medium'>시나리오</th>
                <th className='p-3 text-center font-medium'>유형</th>
                <th className='p-3 text-center font-medium'>상태</th>
                <th className='p-3 text-right font-medium'>생성일</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr>
                  <td
                    colSpan={6}
                    className='p-10 text-center text-muted-foreground'
                  >
                    캠페인이 없습니다.
                  </td>
                </tr>
              ) : (
                items.map((c) => (
                  <tr
                    key={c.id}
                    className='cursor-pointer border-b hover:bg-muted/50'
                  >
                    <td className='max-w-[250px] truncate p-3'>
                      {c.video_title || c.id}
                    </td>
                    <td className='p-3'>{c.brand_name || '-'}</td>
                    <td className='p-3 text-center'>
                      <Badge variant='outline'>{c.scenario}</Badge>
                    </td>
                    <td className='p-3 text-center'>
                      <Badge variant='outline'>
                        {c.campaign_type || 'scenario'}
                      </Badge>
                    </td>
                    <td className='p-3 text-center'>
                      <Badge variant={statusColor(c.status)}>
                        {c.status}
                      </Badge>
                    </td>
                    <td className='p-3 text-right text-muted-foreground'>
                      {c.created_at
                        ? new Date(c.created_at).toLocaleDateString('ko')
                        : '-'}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  )

  return (
    <>
      <Header fixed>
        <div className='ml-auto flex items-center space-x-4'>
          <ThemeSwitch />
          <ProfileDropdown />
        </div>
      </Header>
      <Main>
        <div className='mb-2 flex flex-wrap items-center justify-between space-y-2'>
          <div>
            <h2 className='text-2xl font-bold tracking-tight'>캠페인</h2>
            <p className='text-muted-foreground'>
              시나리오 캠페인 + 다이렉트 캠페인
            </p>
          </div>
          <div className='flex gap-2'>
            <Button variant='outline'>
              <Zap className='mr-2 h-4 w-4' /> 다이렉트
            </Button>
            <Button>
              <Plus className='mr-2 h-4 w-4' /> 캠페인 생성
            </Button>
          </div>
        </div>

        <Tabs defaultValue='all'>
          <TabsList>
            <TabsTrigger value='all'>전체</TabsTrigger>
            <TabsTrigger value='scenario'>시나리오</TabsTrigger>
            <TabsTrigger value='direct'>다이렉트</TabsTrigger>
          </TabsList>
          <TabsContent value='all' className='mt-4'>
            {campaignTable(campaigns)}
          </TabsContent>
          <TabsContent value='scenario' className='mt-4'>
            {campaignTable(
              campaigns.filter((c) => c.campaign_type !== 'direct')
            )}
          </TabsContent>
          <TabsContent value='direct' className='mt-4'>
            {campaignTable(
              campaigns.filter((c) => c.campaign_type === 'direct')
            )}
          </TabsContent>
        </Tabs>
      </Main>
    </>
  )
}
