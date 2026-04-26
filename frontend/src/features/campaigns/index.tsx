import { useEffect, useState } from 'react'
import { Plus, Zap, Pause, Play, Square } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { fetchApi } from '@/lib/api'
import { useCountUp } from '@/hooks/use-count-up'
import { CampaignCreateDialog } from './campaign-create-dialog'
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
  worker_name?: string
  target_count?: number
  duration_days?: number
}

const statusLabel: Record<string, string> = {
  in_progress: '진행중',
  completed: '완료',
  planning: '준비중',
  failed: '실패',
  paused: '일시정지',
}
const statusTag: Record<string, string> = {
  in_progress: 'hydra-tag-primary',
  completed: 'hydra-tag-success',
  planning: 'hydra-tag-muted',
  failed: 'hydra-tag-danger',
  paused: 'hydra-tag-warning',
}

function CampaignStatCard({ label, value }: { label: string; value: number }) {
  const animated = useCountUp(value)
  return (
    <div className='hydra-stat-card hydra-card-hover'>
      <span className='hydra-stat-label'>{label}</span>
      <div className='hydra-stat-value hydra-num-anim'>{animated}</div>
    </div>
  )
}

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [loading, setLoading] = useState(true)
  const [createOpen, setCreateOpen] = useState(false)
  const [directOpen, setDirectOpen] = useState(false)
  const [detailId, setDetailId] = useState<number | null>(null)

  const loadCampaigns = () => {
    setLoading(true)
    fetchApi<{ items: Campaign[]; total: number }>('/campaigns/api/list')
      .then((data) => setCampaigns(data.items || []))
      .catch(() => setCampaigns([]))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadCampaigns()
  }, [])

  const inProgress = campaigns.filter(c => c.status === 'in_progress').length
  const completed = campaigns.filter(c => c.status === 'completed').length
  const total = campaigns.length

  return (
    <>
      <Header fixed>
        <div className='ml-auto flex items-center space-x-4'>
          <ThemeSwitch />
          <ProfileDropdown />
        </div>
      </Header>
      <Main>
        <div >
          <div className='mb-5 flex flex-wrap items-center justify-between gap-2'>
            <div>
              <h2 className='text-[22px] font-bold hydra-page-h'>캠페인</h2>
              <p className='text-muted-foreground text-[13px]'>
                어디에, 어떻게, 얼마나 작업할지 관리하세요
              </p>
            </div>
            <div className='flex gap-2'>
              <Button size="lg" variant='outline' onClick={() => setDirectOpen(true)} className='hydra-btn-press'>
                <Zap className='mr-2 h-4 w-4' /> 다이렉트
              </Button>
              <Button size="lg" onClick={() => setCreateOpen(true)} className='hydra-btn-press'>
                <Plus className='mr-2 h-4 w-4' /> 캠페인 만들기
              </Button>
            </div>
          </div>

          {/* Stat Cards */}
          <div className='grid grid-cols-3 gap-3 mb-5'>
            <CampaignStatCard label='전체 캠페인' value={total} />
            <CampaignStatCard label='진행중' value={inProgress} />
            <CampaignStatCard label='완료' value={completed} />
          </div>

          {loading ? (
            <div className='space-y-3'>
              {[1, 2, 3].map(i => (
                <Skeleton key={i} className='h-28 rounded-xl' />
              ))}
            </div>
          ) : campaigns.length === 0 ? (
            <div className='hydra-empty'>
              <div className='hydra-empty-icon'>📋</div>
              <div className='hydra-empty-title'>아직 캠페인이 없어요</div>
              <div className='hydra-empty-desc'>
                브랜드를 등록하고 첫 캠페인을 만들어보세요. 다이렉트로 빠르게 만들 수도 있어요.
              </div>
              <div className='flex gap-2 mt-2'>
                <Button onClick={() => setDirectOpen(true)} variant='outline' className='hydra-btn-press'>
                  <Zap className='mr-2 h-4 w-4' /> 다이렉트
                </Button>
                <Button onClick={() => setCreateOpen(true)} className='hydra-btn-press'>
                  <Plus className='mr-2 h-4 w-4' /> 캠페인 만들기
                </Button>
              </div>
            </div>
          ) : (
            <div className='space-y-3'>
              {campaigns.map(c => {
                const progress = c.total_tasks && c.total_tasks > 0
                  ? Math.round((c.completed_tasks ?? 0) / c.total_tasks * 100) : 0
                return (
                  <div
                    key={c.id}
                    className='bg-card border border-border rounded-xl p-5 hydra-card-hover cursor-pointer'
                    onClick={() => setDetailId(detailId === c.id ? null : c.id)}
                  >
                    <div className='flex items-center justify-between mb-2'>
                      <div className='flex items-center gap-2'>
                        <span className='text-foreground font-semibold text-[15px]'>
                          {c.brand_name || '브랜드 미지정'} — {c.video_title || `캠페인 #${c.id}`}
                        </span>
                        <span className={`hydra-tag ${statusTag[c.status] || 'hydra-tag-muted'}`}>
                          {statusLabel[c.status] || c.status}
                        </span>
                        <span className={`hydra-tag ${c.campaign_type === 'direct' ? 'hydra-tag-warning' : 'hydra-tag-blue'}`}>
                          {c.campaign_type === 'direct' ? '다이렉트' : `프리셋 ${c.scenario}`}
                        </span>
                      </div>
                      <span className='text-muted-foreground text-[12px]'>
                        {c.created_at ? new Date(c.created_at).toLocaleDateString('ko') : ''}
                      </span>
                    </div>

                    {/* Progress */}
                    <div className='hydra-progress-bar mb-2'>
                      <div
                        className='hydra-progress-fill bg-gradient-to-r from-primary to-green-500'
                        style={{ width: `${progress}%` }}
                      />
                    </div>
                    <div className='flex items-center justify-between text-[12px] text-muted-foreground'>
                      <span>{c.completed_tasks ?? 0}/{c.total_tasks ?? 0} 태스크 · {progress}%</span>
                      {c.worker_name && <span className='text-primary'>{c.worker_name}</span>}
                    </div>

                    {/* Detail Section */}
                    {detailId === c.id && (
                      <div className='mt-4 pt-4 border-t border-border/50'>
                        <div className='grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4'>
                          <div className='bg-background rounded-lg border border-border/50 p-3 text-center'>
                            <div className='text-[18px] font-bold'>{c.completed_tasks ?? 0}</div>
                            <div className='text-[11px] text-muted-foreground'>완료 태스크</div>
                          </div>
                          <div className='bg-background rounded-lg border border-border/50 p-3 text-center'>
                            <div className='text-[18px] font-bold'>{c.total_tasks ?? 0}</div>
                            <div className='text-[11px] text-muted-foreground'>전체 태스크</div>
                          </div>
                          <div className='bg-background rounded-lg border border-border/50 p-3 text-center'>
                            <div className='text-[18px] font-bold'>{progress}%</div>
                            <div className='text-[11px] text-muted-foreground'>진행률</div>
                          </div>
                          <div className='bg-background rounded-lg border border-border/50 p-3 text-center'>
                            <div className='text-[18px] font-bold'>{c.scenario || '-'}</div>
                            <div className='text-[11px] text-muted-foreground'>프리셋</div>
                          </div>
                        </div>
                        <div className='flex gap-2'>
                          {c.status === 'in_progress' && (
                            <Button variant='outline' size='sm' className='hydra-btn-press'>
                              <Pause className='mr-1 h-3 w-3' /> 일시정지
                            </Button>
                          )}
                          {c.status === 'paused' && (
                            <Button variant='outline' size='sm' className='hydra-btn-press'>
                              <Play className='mr-1 h-3 w-3' /> 재개
                            </Button>
                          )}
                          {(c.status === 'in_progress' || c.status === 'paused') && (
                            <Button variant='outline' size='sm' className='text-destructive hover:text-destructive hydra-btn-press'>
                              <Square className='mr-1 h-3 w-3' /> 중단
                            </Button>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </Main>

      <CampaignCreateDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onSuccess={loadCampaigns}
      />
      <DirectCampaignDialog
        open={directOpen}
        onOpenChange={setDirectOpen}
        onSuccess={loadCampaigns}
      />
    </>
  )
}
