import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import {
  Sheet, SheetContent, SheetHeader, SheetTitle,
} from '@/components/ui/sheet'
import { fetchApi } from '@/lib/api'

interface AccountDetail {
  id: number
  name: string
  email: string
  status: string
  adspower_profile_id: string | null
  current_pc: string | null
  persona_name: string | null
  created_at: string | null
}

interface AccountMetrics {
  total_comments: number
  total_likes: number
  success_rate: number
  health_score: number
}

interface ActivityEntry {
  id: number
  action: string
  result: string
  created_at: string
}

interface AccountDetailSheetProps {
  accountId: number | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

const statusLabels: Record<string, string> = {
  active: '활성', warmup: '워밍업', cooldown: '쿨다운',
  retired: '정지', ghost: '고스트', registered: '등록됨',
}
const statusTagClass: Record<string, string> = {
  active: 'hydra-tag-success', warmup: 'hydra-tag-warning', cooldown: 'hydra-tag-blue',
  retired: 'hydra-tag-danger', ghost: 'hydra-tag-ghost', registered: 'hydra-tag-muted',
}
const statusActions = ['active', 'cooldown', 'retired'] as const
const statusActionLabels: Record<string, string> = {
  active: '활성화', cooldown: '쿨다운', retired: '정지',
}

export function AccountDetailSheet({ accountId, open, onOpenChange }: AccountDetailSheetProps) {
  const [detail, setDetail] = useState<AccountDetail | null>(null)
  const [metrics, setMetrics] = useState<AccountMetrics | null>(null)
  const [history, setHistory] = useState<ActivityEntry[]>([])
  const [changingStatus, setChangingStatus] = useState(false)
  const [deleteConfirm, setDeleteConfirm] = useState(false)

  useEffect(() => {
    if (!accountId || !open) return
    setDetail(null)
    setMetrics(null)
    setHistory([])
    setDeleteConfirm(false)

    fetchApi<AccountDetail>(`/accounts/api/${accountId}`).then(setDetail).catch(() => {})
    fetchApi<AccountMetrics>(`/accounts/api/${accountId}/metrics`).then(setMetrics).catch(() => {})
    fetchApi<{ items: ActivityEntry[] }>(`/accounts/api/${accountId}/history`)
      .then(data => setHistory(data.items || []))
      .catch(() => {})
  }, [accountId, open])

  const changeStatus = async (newStatus: string) => {
    if (!accountId) return
    setChangingStatus(true)
    try {
      await fetchApi(`/accounts/api/${accountId}/status`, {
        method: 'POST',
        body: JSON.stringify({ status: newStatus }),
      })
      setDetail(prev => prev ? { ...prev, status: newStatus } : prev)
    } catch { /* error */ }
    finally { setChangingStatus(false) }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className='overflow-y-auto sm:max-w-md'>
        <SheetHeader>
          <SheetTitle>{detail?.name || '계정 상세'}</SheetTitle>
        </SheetHeader>

        {detail ? (
          <div className='space-y-5 px-4 pb-4'>
            {/* Info */}
            <section>
              <h4 className='text-foreground font-semibold text-[14px] mb-3'>계정 정보</h4>
              <div className='space-y-2 text-[13px]'>
                {[
                  ['이메일', detail.email || '-'],
                  ['상태', null],
                  ['AdsPower 프로필', detail.adspower_profile_id || '-'],
                  ['현재 PC', detail.current_pc || '-'],
                  ['페르소나', detail.persona_name || '-'],
                ].map(([label, value], i) => (
                  <div key={i} className='flex justify-between'>
                    <span className='text-muted-foreground'>{label}</span>
                    {label === '상태' ? (
                      <span className={`hydra-tag ${statusTagClass[detail.status] || 'hydra-tag-muted'}`}>
                        {statusLabels[detail.status] || detail.status}
                      </span>
                    ) : (
                      <span className={label === 'AdsPower 프로필' ? 'font-mono text-[12px]' : ''}>
                        {value}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </section>

            <Separator />

            {/* Metrics */}
            <section>
              <h4 className='text-foreground font-semibold text-[14px] mb-3'>작업 통계</h4>
              {metrics ? (
                <div className='grid grid-cols-2 gap-2'>
                  {[
                    ['총 댓글', metrics.total_comments],
                    ['총 좋아요', metrics.total_likes],
                    ['성공률', `${metrics.success_rate}%`],
                    ['건강도', metrics.health_score],
                  ].map(([label, value], i) => (
                    <div key={i} className='bg-background border border-border/50 rounded-lg p-3 text-center'>
                      <div className='text-[18px] font-bold'>{value}</div>
                      <div className='text-[11px] text-muted-foreground'>{label}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className='py-3'>
                  <div className='hydra-skeleton h-20 rounded-lg' />
                </div>
              )}
            </section>

            <Separator />

            {/* Status Change */}
            <section>
              <h4 className='text-foreground font-semibold text-[14px] mb-3'>상태 변경</h4>
              <div className='flex gap-2'>
                {statusActions.map(s => (
                  <Button
                    key={s}
                    size='sm'
                    variant={detail.status === s ? 'default' : 'outline'}
                    disabled={detail.status === s || changingStatus}
                    onClick={() => changeStatus(s)}
                    className='hydra-btn-press'
                  >
                    {statusActionLabels[s]}
                  </Button>
                ))}
              </div>
            </section>

            <Separator />

            {/* Activity */}
            <section>
              <h4 className='text-foreground font-semibold text-[14px] mb-3'>최근 활동</h4>
              {history.length === 0 ? (
                <p className='text-muted-foreground text-[13px] text-center py-4'>활동 이력이 없어요</p>
              ) : (
                <div className='space-y-2'>
                  {history.slice(0, 20).map(entry => (
                    <div key={entry.id} className='flex items-center justify-between rounded-lg border border-border/50 px-3 py-2 text-[13px]'>
                      <div>
                        <span className='font-medium'>{entry.action}</span>
                        <span className='ml-2 text-muted-foreground'>{entry.result}</span>
                      </div>
                      <span className='text-muted-foreground text-[11px]'>
                        {new Date(entry.created_at).toLocaleString('ko')}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <Separator />

            {/* Delete */}
            <section>
              <Button
                variant='ghost'
                className={`w-full text-destructive hover:text-destructive hover:bg-destructive/10 hydra-btn-press ${deleteConfirm ? 'bg-destructive/10' : ''}`}
                onClick={() => {
                  if (!deleteConfirm) { setDeleteConfirm(true); return }
                  changeStatus('retired')
                  onOpenChange(false)
                }}
              >
                {deleteConfirm ? '정말 폐기할까요?' : '계정 폐기'}
              </Button>
            </section>
          </div>
        ) : (
          <div className='space-y-3 px-4 py-6'>
            <div className='hydra-skeleton h-6 w-40 rounded' />
            <div className='hydra-skeleton h-4 w-full rounded' />
            <div className='hydra-skeleton h-4 w-3/4 rounded' />
            <div className='hydra-skeleton h-20 w-full rounded-lg mt-4' />
          </div>
        )}
      </SheetContent>
    </Sheet>
  )
}
