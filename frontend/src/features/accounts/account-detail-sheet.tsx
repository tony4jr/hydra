import { useEffect, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
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

const statusOptions = ['active', 'cooldown', 'retired'] as const

const statusColor = (s: string) => {
  switch (s) {
    case 'active':
      return 'default' as const
    case 'warmup':
      return 'secondary' as const
    case 'cooldown':
      return 'outline' as const
    case 'retired':
      return 'destructive' as const
    default:
      return 'secondary' as const
  }
}

export function AccountDetailSheet({
  accountId,
  open,
  onOpenChange,
}: AccountDetailSheetProps) {
  const [detail, setDetail] = useState<AccountDetail | null>(null)
  const [metrics, setMetrics] = useState<AccountMetrics | null>(null)
  const [history, setHistory] = useState<ActivityEntry[]>([])
  const [changingStatus, setChangingStatus] = useState(false)

  useEffect(() => {
    if (!accountId || !open) return

    setDetail(null)
    setMetrics(null)
    setHistory([])

    fetchApi<AccountDetail>(`/accounts/api/${accountId}`)
      .then(setDetail)
      .catch(() => {})

    fetchApi<AccountMetrics>(`/accounts/api/${accountId}/metrics`)
      .then(setMetrics)
      .catch(() => {})

    fetchApi<{ items: ActivityEntry[] }>(`/accounts/api/${accountId}/history`)
      .then((data) => setHistory(data.items || []))
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
      setDetail((prev) => (prev ? { ...prev, status: newStatus } : prev))
    } catch {
      alert('상태 변경 실패')
    } finally {
      setChangingStatus(false)
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className='overflow-y-auto sm:max-w-md'>
        <SheetHeader>
          <SheetTitle>{detail?.name || '계정 상세'}</SheetTitle>
          <SheetDescription>
            계정 정보, 통계 및 활동 이력
          </SheetDescription>
        </SheetHeader>

        {detail ? (
          <div className='space-y-6 px-4 pb-4'>
            {/* Account Info */}
            <section className='space-y-3'>
              <h4 className='text-sm font-semibold'>계정 정보</h4>
              <div className='space-y-2 text-sm'>
                <div className='flex justify-between'>
                  <span className='text-muted-foreground'>이메일</span>
                  <span>{detail.email || '-'}</span>
                </div>
                <div className='flex justify-between'>
                  <span className='text-muted-foreground'>상태</span>
                  <Badge variant={statusColor(detail.status)}>
                    {detail.status}
                  </Badge>
                </div>
                <div className='flex justify-between'>
                  <span className='text-muted-foreground'>
                    AdsPower 프로필
                  </span>
                  <span className='font-mono'>
                    {detail.adspower_profile_id || '-'}
                  </span>
                </div>
                <div className='flex justify-between'>
                  <span className='text-muted-foreground'>현재 PC</span>
                  <span>{detail.current_pc || '-'}</span>
                </div>
                <div className='flex justify-between'>
                  <span className='text-muted-foreground'>페르소나</span>
                  <span>{detail.persona_name || '-'}</span>
                </div>
              </div>
            </section>

            <Separator />

            {/* Metrics */}
            <section className='space-y-3'>
              <h4 className='text-sm font-semibold'>작업 통계</h4>
              {metrics ? (
                <div className='grid grid-cols-2 gap-3'>
                  <div className='rounded-lg border p-3 text-center'>
                    <div className='text-2xl font-bold'>
                      {metrics.total_comments}
                    </div>
                    <div className='text-xs text-muted-foreground'>
                      총 댓글
                    </div>
                  </div>
                  <div className='rounded-lg border p-3 text-center'>
                    <div className='text-2xl font-bold'>
                      {metrics.total_likes}
                    </div>
                    <div className='text-xs text-muted-foreground'>
                      총 좋아요
                    </div>
                  </div>
                  <div className='rounded-lg border p-3 text-center'>
                    <div className='text-2xl font-bold'>
                      {metrics.success_rate}%
                    </div>
                    <div className='text-xs text-muted-foreground'>
                      성공률
                    </div>
                  </div>
                  <div className='rounded-lg border p-3 text-center'>
                    <div className='text-2xl font-bold'>
                      {metrics.health_score}
                    </div>
                    <div className='text-xs text-muted-foreground'>
                      건강도
                    </div>
                  </div>
                </div>
              ) : (
                <p className='text-sm text-muted-foreground'>
                  통계 로딩 중...
                </p>
              )}
            </section>

            <Separator />

            {/* Status Change */}
            <section className='space-y-3'>
              <h4 className='text-sm font-semibold'>상태 변경</h4>
              <div className='flex gap-2'>
                {statusOptions.map((s) => (
                  <Button
                    key={s}
                    size='sm'
                    variant={detail.status === s ? 'default' : 'outline'}
                    disabled={detail.status === s || changingStatus}
                    onClick={() => changeStatus(s)}
                  >
                    {s}
                  </Button>
                ))}
              </div>
            </section>

            <Separator />

            {/* Activity History */}
            <section className='space-y-3'>
              <h4 className='text-sm font-semibold'>최근 활동 이력</h4>
              {history.length === 0 ? (
                <p className='text-sm text-muted-foreground'>
                  활동 이력이 없습니다.
                </p>
              ) : (
                <div className='space-y-2'>
                  {history.slice(0, 20).map((entry) => (
                    <div
                      key={entry.id}
                      className='flex items-center justify-between rounded border px-3 py-2 text-sm'
                    >
                      <div>
                        <span className='font-medium'>{entry.action}</span>
                        <span className='ml-2 text-muted-foreground'>
                          {entry.result}
                        </span>
                      </div>
                      <span className='text-xs text-muted-foreground'>
                        {new Date(entry.created_at).toLocaleString('ko')}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>
        ) : (
          <div className='flex items-center justify-center py-10 text-muted-foreground'>
            로딩 중...
          </div>
        )}
      </SheetContent>
    </Sheet>
  )
}
