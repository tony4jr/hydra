import { useEffect, useState } from 'react'
import { ChevronDown, ChevronRight, Zap } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { fetchApi } from '@/lib/api'
import { DirectCampaignDialog } from './direct-campaign-dialog'

interface Campaign {
  id: number
  video_title: string
  brand_name: string
  scenario: string
  campaign_type: string
  status: string
  created_at: string
  total_tasks?: number
  completed_tasks?: number
}

interface CampaignListResponse {
  items: Campaign[]
  total: number
}

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [directOpen, setDirectOpen] = useState(false)

  const loadCampaigns = () => {
    fetchApi<CampaignListResponse>('/campaigns/api/list')
      .then((data) => setCampaigns(data.items || []))
      .catch(() => {})
  }

  useEffect(() => {
    loadCampaigns()
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

  const toggleExpand = (id: number) => {
    setExpandedId((prev) => (prev === id ? null : id))
  }

  const campaignTable = (items: Campaign[]) => (
    <Card>
      <CardContent className='p-0'>
        <div className='overflow-auto'>
          <table className='w-full text-sm'>
            <thead>
              <tr className='border-b bg-muted/50'>
                <th className='w-8 p-3'></th>
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
                    colSpan={7}
                    className='p-10 text-center text-muted-foreground'
                  >
                    캠페인이 없습니다.
                  </td>
                </tr>
              ) : (
                items.map((c) => (
                  <>
                    <tr
                      key={c.id}
                      className='cursor-pointer border-b hover:bg-muted/50'
                      onClick={() => toggleExpand(c.id)}
                    >
                      <td className='p-3'>
                        {expandedId === c.id ? (
                          <ChevronDown className='h-4 w-4 text-muted-foreground' />
                        ) : (
                          <ChevronRight className='h-4 w-4 text-muted-foreground' />
                        )}
                      </td>
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
                    {expandedId === c.id && (
                      <tr key={`${c.id}-detail`} className='border-b'>
                        <td colSpan={7} className='bg-muted/30 px-6 py-4'>
                          <div className='grid gap-2 text-sm'>
                            <div className='flex gap-8'>
                              <div>
                                <span className='text-muted-foreground'>
                                  캠페인 ID:{' '}
                                </span>
                                <strong>{c.id}</strong>
                              </div>
                              <div>
                                <span className='text-muted-foreground'>
                                  유형:{' '}
                                </span>
                                <strong>
                                  {c.campaign_type || 'scenario'}
                                </strong>
                              </div>
                              {c.total_tasks != null && (
                                <div>
                                  <span className='text-muted-foreground'>
                                    진행률:{' '}
                                  </span>
                                  <strong>
                                    {c.completed_tasks ?? 0}/{c.total_tasks}
                                  </strong>
                                </div>
                              )}
                            </div>
                            <div>
                              <span className='text-muted-foreground'>
                                시나리오:{' '}
                              </span>
                              {c.scenario || '-'}
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
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
              시나리오 캠페인은 브랜드 주간 목표 기반으로 자동 생성됩니다
            </p>
          </div>
          <div className='flex gap-2'>
            <Button onClick={() => setDirectOpen(true)}>
              <Zap className='mr-2 h-4 w-4' /> 다이렉트
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

      <DirectCampaignDialog
        open={directOpen}
        onOpenChange={setDirectOpen}
        onSuccess={loadCampaigns}
      />
    </>
  )
}
