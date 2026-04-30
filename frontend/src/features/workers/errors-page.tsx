import { useEffect, useState } from 'react'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { fetchApi, http } from '@/lib/api'

interface WorkerError {
  id: number
  worker_id: number
  worker_name: string
  kind: string
  message: string
  traceback: string | null
  context: Record<string, unknown> | null
  screenshot_url: string | null
  occurred_at: string
  received_at: string
}

const KIND_COLORS: Record<string, string> = {
  heartbeat_fail: 'bg-yellow-500/20 text-yellow-700 dark:text-yellow-400',
  fetch_fail: 'bg-orange-500/20 text-orange-700 dark:text-orange-400',
  task_fail: 'bg-red-500/20 text-red-700 dark:text-red-400',
  diagnostic: 'bg-blue-500/20 text-blue-700 dark:text-blue-400',
  update_fail: 'bg-purple-500/20 text-purple-700 dark:text-purple-400',
  other: 'bg-muted text-muted-foreground',
}

function relativeTime(iso: string): string {
  const d = new Date(iso)
  const diff = Date.now() - d.getTime()
  const sec = Math.floor(diff / 1000)
  if (sec < 60) return `${sec}s 전`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m 전`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr}h 전`
  return d.toLocaleString('ko-KR')
}

export default function WorkerErrorsPage() {
  const [errors, setErrors] = useState<WorkerError[]>([])
  const [loading, setLoading] = useState(true)
  const [filterKind, setFilterKind] = useState<string>('')
  const [selected, setSelected] = useState<WorkerError | null>(null)
  const [imgUrl, setImgUrl] = useState<string | null>(null)

  const loadErrors = async () => {
    try {
      const params: Record<string, string> = { limit: '200' }
      if (filterKind) params.kind = filterKind
      const data = await fetchApi<WorkerError[]>(
        `/api/admin/workers/errors?${new URLSearchParams(params)}`,
      )
      setErrors(data)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadErrors()
    const id = setInterval(loadErrors, 10_000)
    return () => clearInterval(id)
  }, [filterKind])

  // 모달이 열리면 스크린샷 fetch (JWT 인증 필요해서 blob URL 만듦)
  useEffect(() => {
    if (!selected?.screenshot_url) {
      setImgUrl(null)
      return
    }
    let revoked = ''
    http
      .get(`/api/admin/workers/errors/screenshot/${selected.screenshot_url}`, {
        responseType: 'blob',
      })
      .then((r) => {
        const url = URL.createObjectURL(r.data)
        revoked = url
        setImgUrl(url)
      })
      .catch(() => setImgUrl(null))
    return () => {
      if (revoked) URL.revokeObjectURL(revoked)
    }
  }, [selected])

  const kinds = ['', 'task_fail', 'fetch_fail', 'heartbeat_fail', 'diagnostic', 'update_fail', 'other']

  return (
    <>
      <Header>
        <div className='ms-auto flex items-center space-x-4'>
          <ThemeSwitch />
          <ProfileDropdown />
        </div>
      </Header>
      <Main>
        <div className='mb-4'>
          <h1 className='hydra-page-h'>워커 에러</h1>
          <p className='hydra-page-sub'>
            워커가 보고한 에러/진단 로그. 10초마다 자동 갱신.
          </p>
        </div>

        <div className='mb-4 flex gap-2'>
          {kinds.map((k) => (
            <Button
              key={k || 'all'}
              variant={filterKind === k ? 'default' : 'outline'}
              size='sm'
              onClick={() => setFilterKind(k)}
            >
              {k || '전체'}
            </Button>
          ))}
          <Button size='sm' variant='ghost' onClick={loadErrors}>
            ↻ 새로고침
          </Button>
        </div>

        <div className='bg-card rounded-xl border'>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className='w-[120px]'>시각</TableHead>
                <TableHead className='w-[140px]'>워커</TableHead>
                <TableHead className='w-[110px]'>종류</TableHead>
                <TableHead>메시지</TableHead>
                <TableHead className='w-[60px]'>📷</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading && (
                <TableRow>
                  <TableCell colSpan={5}>
                    <Skeleton className='h-8 w-full' />
                  </TableCell>
                </TableRow>
              )}
              {!loading && errors.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className='text-muted-foreground py-8 text-center'>
                    에러 없음
                  </TableCell>
                </TableRow>
              )}
              {errors.map((e) => (
                <TableRow
                  key={e.id}
                  onClick={() => setSelected(e)}
                  className='cursor-pointer'
                >
                  <TableCell className='text-muted-foreground text-xs'>
                    {relativeTime(e.received_at)}
                  </TableCell>
                  <TableCell className='font-mono text-xs'>{e.worker_name}</TableCell>
                  <TableCell>
                    <Badge className={KIND_COLORS[e.kind] || KIND_COLORS.other}>
                      {e.kind}
                    </Badge>
                  </TableCell>
                  <TableCell className='max-w-[600px] truncate font-mono text-xs'>
                    {e.message}
                  </TableCell>
                  <TableCell className='text-center'>
                    {e.screenshot_url ? '✓' : ''}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Main>

      <Dialog open={!!selected} onOpenChange={(o) => !o && setSelected(null)}>
        <DialogContent className='max-w-3xl'>
          <DialogHeader>
            <DialogTitle>
              <Badge className={KIND_COLORS[selected?.kind || 'other']}>
                {selected?.kind}
              </Badge>{' '}
              {selected?.worker_name}
            </DialogTitle>
          </DialogHeader>
          {selected && (
            <div className='space-y-3 text-sm'>
              <div>
                <div className='text-muted-foreground text-xs'>메시지</div>
                <div className='bg-muted/50 rounded p-2 font-mono'>{selected.message}</div>
              </div>
              <div>
                <div className='text-muted-foreground text-xs'>발생 시각</div>
                <div className='font-mono text-xs'>
                  {new Date(selected.occurred_at).toLocaleString('ko-KR')} →{' '}
                  {new Date(selected.received_at).toLocaleString('ko-KR')}
                </div>
              </div>
              {selected.context && (
                <div>
                  <div className='text-muted-foreground text-xs'>Context</div>
                  <pre className='bg-muted/50 max-h-48 overflow-auto rounded p-2 text-xs'>
                    {JSON.stringify(selected.context, null, 2)}
                  </pre>
                </div>
              )}
              {selected.traceback && (
                <div>
                  <div className='text-muted-foreground text-xs'>Traceback</div>
                  <pre className='bg-muted/50 max-h-64 overflow-auto rounded p-2 text-xs'>
                    {selected.traceback}
                  </pre>
                </div>
              )}
              {selected.screenshot_url && (
                <div>
                  <div className='text-muted-foreground text-xs'>스크린샷</div>
                  {imgUrl ? (
                    <img
                      src={imgUrl}
                      alt='screenshot'
                      className='border-border max-h-[60vh] rounded border'
                    />
                  ) : (
                    <Skeleton className='h-48 w-full' />
                  )}
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}
