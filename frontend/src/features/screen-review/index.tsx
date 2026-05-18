/**
 * Phase 3.4 — Screen Review (UNKNOWN_SCREEN 라벨링 큐).
 *
 * 학습 루프 운영자 진입점:
 *   1. 미라벨 UNKNOWN 목록 (10초 polling)
 *   2. 클릭 → 스크린샷 + context 확인
 *   3. 라벨 → ScreenResolution 생성 → 워커가 다음부터 자동 처리
 *
 * 의도적으로 errors-page 와 분리: 흐름이 디버깅 ≠ 학습. 메뉴도 따로.
 */
import { useEffect, useState } from 'react'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { fetchApi, http } from '@/lib/api'

interface UnknownScreenItem {
  id: number
  worker_id: number
  screen_state: string | null
  failure_taxonomy: string | null
  message: string
  captured_url: string | null
  captured_title: string | null
  screenshot_url: string | null
  context: Record<string, unknown> | null
  received_at: string
}

const RESOLUTION_TYPES = [
  'auto_click_skip',
  'auto_enter_code',
  'escalate_manual',
  'fail_task',
  'retry_after_cooldown',
] as const

type ResolutionType = (typeof RESOLUTION_TYPES)[number]

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const sec = Math.floor(diff / 1000)
  if (sec < 60) return `${sec}s 전`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m 전`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr}h 전`
  return new Date(iso).toLocaleString('ko-KR')
}

export default function ScreenReviewPage() {
  const [items, setItems] = useState<UnknownScreenItem[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<UnknownScreenItem | null>(null)
  const [imgUrl, setImgUrl] = useState<string | null>(null)

  // 라벨 폼 state (selected 가 바뀌면 reset)
  const [labelState, setLabelState] = useState('')
  const [resolutionType, setResolutionType] = useState<ResolutionType>('auto_click_skip')
  const [urlPattern, setUrlPattern] = useState('')
  const [titlePattern, setTitlePattern] = useState('')
  const [selector, setSelector] = useState('')
  const [notes, setNotes] = useState('')
  const [approved, setApproved] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState('')

  const load = async () => {
    try {
      const data = await fetchApi<UnknownScreenItem[]>(
        '/api/admin/screen-review/list?only_unresolved=true&limit=100&hours=168',
      )
      setItems(data)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    const id = setInterval(load, 10_000)
    return () => clearInterval(id)
  }, [])

  // 모달 열릴 때 스크린샷 + 폼 reset
  useEffect(() => {
    if (!selected) {
      setImgUrl(null)
      return
    }
    setLabelState(selected.screen_state || '')
    setResolutionType('auto_click_skip')
    setUrlPattern('')
    setTitlePattern('')
    setSelector('')
    setNotes('')
    setApproved(true)
    setSaveMsg('')

    if (!selected.screenshot_url) return
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

  const submitLabel = async () => {
    if (!selected) return
    if (!labelState.trim()) {
      setSaveMsg('screen_state 가 비어있어요')
      return
    }
    setSaving(true)
    setSaveMsg('')
    try {
      const action_config = selector.trim()
        ? { selector: selector.trim() }
        : null
      await http.post(`/api/admin/screen-review/${selected.id}/label`, {
        screen_state: labelState.trim(),
        resolution_type: resolutionType,
        url_pattern: urlPattern.trim() || null,
        title_pattern: titlePattern.trim() || null,
        dom_signature: null,
        action_config,
        approved,
        notes: notes.trim() || null,
      })
      setSaveMsg('저장 완료')
      setSelected(null)
      await load()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      setSaveMsg(`실패: ${msg}`)
    } finally {
      setSaving(false)
    }
  }

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
          <h1 className='hydra-page-h'>Screen Review</h1>
          <p className='hydra-page-sub'>
            모르는 화면(UNKNOWN_SCREEN) 라벨링 큐. 라벨 → 워커가 다음부터 자동 처리.
          </p>
        </div>

        <div className='mb-4 flex gap-2'>
          <Button size='sm' variant='ghost' onClick={load}>↻ 새로고침</Button>
          <span className='text-muted-foreground text-xs self-center'>
            {items.length}건 미라벨 / 10초마다 자동 갱신
          </span>
        </div>

        <div className='bg-card rounded-xl border'>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className='w-[120px]'>시각</TableHead>
                <TableHead className='w-[200px]'>screen_state</TableHead>
                <TableHead className='w-[140px]'>taxonomy</TableHead>
                <TableHead>URL</TableHead>
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
              {!loading && items.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className='text-muted-foreground py-8 text-center'>
                    미라벨 화면 없음 (전부 처리됨)
                  </TableCell>
                </TableRow>
              )}
              {items.map((it) => (
                <TableRow
                  key={it.id}
                  onClick={() => setSelected(it)}
                  className='cursor-pointer'
                >
                  <TableCell className='text-muted-foreground text-xs'>
                    {relativeTime(it.received_at)}
                  </TableCell>
                  <TableCell className='font-mono text-xs'>
                    {it.screen_state || '—'}
                  </TableCell>
                  <TableCell>
                    {it.failure_taxonomy && (
                      <Badge variant='outline' className='font-mono text-xs'>
                        {it.failure_taxonomy}
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className='max-w-[500px] truncate text-xs'>
                    {it.captured_url}
                  </TableCell>
                  <TableCell className='text-center'>
                    {it.screenshot_url ? '✓' : ''}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Main>

      <Dialog open={!!selected} onOpenChange={(o) => !o && setSelected(null)}>
        <DialogContent className='max-w-4xl max-h-[90vh] overflow-y-auto'>
          <DialogHeader>
            <DialogTitle>
              {selected?.screen_state || 'UNKNOWN'}
            </DialogTitle>
          </DialogHeader>
          {selected && (
            <div className='space-y-4 text-sm'>
              <div className='grid grid-cols-2 gap-2 text-xs'>
                <Row label='URL' value={selected.captured_url} />
                <Row label='Title' value={selected.captured_title} />
                <Row label='Taxonomy' value={selected.failure_taxonomy} />
                <Row label='발생' value={relativeTime(selected.received_at)} />
              </div>
              <div className='bg-muted/50 rounded p-3 text-xs font-mono whitespace-pre-wrap break-all'>
                {selected.message}
              </div>
              {imgUrl && (
                <img
                  src={imgUrl}
                  alt='screenshot'
                  className='w-full rounded border'
                />
              )}

              <div className='space-y-3 border-t pt-4'>
                <h4 className='font-semibold'>라벨링 → ScreenResolution 생성</h4>
                <div className='grid grid-cols-2 gap-3'>
                  <div>
                    <Label className='text-xs'>screen_state</Label>
                    <Input
                      value={labelState}
                      onChange={(e) => setLabelState(e.target.value)}
                      placeholder='trust_device_prompt'
                      className='font-mono text-xs'
                    />
                  </div>
                  <div>
                    <Label className='text-xs'>resolution_type</Label>
                    <Select
                      value={resolutionType}
                      onValueChange={(v) => setResolutionType(v as ResolutionType)}
                    >
                      <SelectTrigger className='text-xs'>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {RESOLUTION_TYPES.map((t) => (
                          <SelectItem key={t} value={t} className='text-xs'>
                            {t}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label className='text-xs'>url_pattern (substring)</Label>
                    <Input
                      value={urlPattern}
                      onChange={(e) => setUrlPattern(e.target.value)}
                      placeholder='/challenge/recaptcha'
                      className='font-mono text-xs'
                    />
                  </div>
                  <div>
                    <Label className='text-xs'>title_pattern (substring)</Label>
                    <Input
                      value={titlePattern}
                      onChange={(e) => setTitlePattern(e.target.value)}
                      placeholder='기기 확인'
                      className='font-mono text-xs'
                    />
                  </div>
                  <div className='col-span-2'>
                    <Label className='text-xs'>
                      selector (auto_click_skip 일 때 필수)
                    </Label>
                    <Input
                      value={selector}
                      onChange={(e) => setSelector(e.target.value)}
                      placeholder="button:has-text('나중에')"
                      className='font-mono text-xs'
                    />
                  </div>
                  <div className='col-span-2'>
                    <Label className='text-xs'>notes</Label>
                    <Textarea
                      value={notes}
                      onChange={(e) => setNotes(e.target.value)}
                      rows={2}
                      className='text-xs'
                    />
                  </div>
                  <div className='col-span-2 flex items-center gap-2'>
                    <input
                      id='approved'
                      type='checkbox'
                      checked={approved}
                      onChange={(e) => setApproved(e.target.checked)}
                    />
                    <Label htmlFor='approved' className='text-xs cursor-pointer'>
                      approved=true (체크해야 워커가 즉시 사용)
                    </Label>
                  </div>
                </div>
              </div>
              {saveMsg && (
                <p className='text-xs text-muted-foreground'>{saveMsg}</p>
              )}
            </div>
          )}
          <DialogFooter>
            <Button variant='ghost' onClick={() => setSelected(null)}>닫기</Button>
            <Button onClick={submitLabel} disabled={saving}>
              {saving ? '저장 중…' : '라벨 저장'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

function Row({ label, value }: { label: string; value?: React.ReactNode }) {
  return (
    <div className='flex gap-2'>
      <span className='text-muted-foreground'>{label}</span>
      <span className='font-mono truncate'>{value || '—'}</span>
    </div>
  )
}
