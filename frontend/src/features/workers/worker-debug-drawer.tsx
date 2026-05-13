import { useEffect, useRef, useState } from 'react'
import { RefreshCw, Terminal, Send, AlertTriangle, Power, Zap, X } from 'lucide-react'
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from '@/components/ui/sheet'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Switch } from '@/components/ui/switch'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { fetchApi } from '@/lib/api'
import { toast } from 'sonner'

interface WorkerSummary {
  id: number
  name: string
  status: string
  verbose_mode: boolean
}

interface LogEntry {
  id: number
  occurred_at: string
  received_at: string
  level: string
  logger_name: string | null
  message: string
}

interface CommandEntry {
  id: number
  command: string
  status: string
  issued_at: string
  delivered_at: string | null
  completed_at: string | null
  result: string | null
  error_message: string | null
}

const LEVEL_COLOR: Record<string, string> = {
  DEBUG: 'text-muted-foreground',
  INFO: 'text-foreground',
  WARNING: 'text-amber-500',
  ERROR: 'text-destructive',
  CRITICAL: 'text-destructive font-bold',
}

function relTime(iso: string): string {
  const t = new Date(iso).getTime()
  const sec = Math.floor((Date.now() - t) / 1000)
  if (sec < 5) return '방금'
  if (sec < 60) return `${sec}초 전`
  if (sec < 3600) return `${Math.floor(sec / 60)}분 전`
  if (sec < 86400) return `${Math.floor(sec / 3600)}시간 전`
  return new Date(iso).toLocaleString('ko')
}

function LogTailTab({ workerId, verbose }: { workerId: number; verbose: boolean }) {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [filter, setFilter] = useState('')
  const [autoScroll, setAutoScroll] = useState(true)
  const lastIdRef = useRef<number | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  const load = async (incremental: boolean) => {
    try {
      const url = incremental && lastIdRef.current != null
        ? `/api/admin/workers/${workerId}/log-tail?after_id=${lastIdRef.current}&limit=200`
        : `/api/admin/workers/${workerId}/log-tail?limit=200`
      const data = await fetchApi<LogEntry[]>(url)
      if (data.length > 0) {
        setLogs(prev => {
          const next = incremental ? [...prev, ...data].slice(-500) : data
          return next
        })
        lastIdRef.current = data[data.length - 1].id
      } else if (!incremental) {
        setLogs([])
      }
    } catch {
      // ignore
    }
  }

  useEffect(() => {
    lastIdRef.current = null
    load(false)
    const id = setInterval(() => load(true), 3000)
    return () => clearInterval(id)
  }, [workerId])

  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [logs, autoScroll])

  const filtered = filter
    ? logs.filter(l => l.message.toLowerCase().includes(filter.toLowerCase())
        || (l.logger_name || '').toLowerCase().includes(filter.toLowerCase())
        || l.level.toLowerCase().includes(filter.toLowerCase()))
    : logs

  return (
    <div className='flex flex-col h-full gap-2'>
      {!verbose && (
        <div className='rounded-md border border-amber-500/30 bg-amber-500/5 p-2 text-xs flex items-start gap-2'>
          <AlertTriangle className='h-4 w-4 text-amber-500 shrink-0 mt-0.5' />
          <span className='text-muted-foreground'>
            Verbose 모드가 꺼져있어 INFO 로그는 새로 안 들어옵니다. 위에서 토글로 켜세요.
            (WARNING+ 에러는 verbose 와 무관하게 별도 보고됩니다)
          </span>
        </div>
      )}
      <div className='flex gap-2 items-center'>
        <Input
          placeholder='로그 필터 (메시지/레벨/로거)'
          value={filter}
          onChange={e => setFilter(e.target.value)}
          className='h-8 text-xs'
        />
        <label className='flex items-center gap-1.5 text-xs text-muted-foreground shrink-0'>
          <input type='checkbox' checked={autoScroll} onChange={e => setAutoScroll(e.target.checked)} />
          자동 스크롤
        </label>
        <Button variant='ghost' size='sm' onClick={() => load(false)} className='h-8 px-2'>
          <RefreshCw className='h-3.5 w-3.5' />
        </Button>
      </div>
      <div
        ref={scrollRef}
        className='flex-1 min-h-0 overflow-y-auto rounded-md border bg-muted/20 p-2 font-mono text-[11px] leading-snug'
      >
        {filtered.length === 0 ? (
          <div className='text-muted-foreground text-center py-8'>
            아직 로그가 없습니다. {verbose ? '몇 초 후 새로고침됩니다.' : 'Verbose 모드를 켜세요.'}
          </div>
        ) : (
          filtered.map(l => (
            <div key={l.id} className='py-0.5 hover:bg-muted/40 rounded px-1'>
              <span className='text-muted-foreground/70 mr-2'>
                {new Date(l.occurred_at).toLocaleTimeString('ko', { hour12: false })}
              </span>
              <span className={`mr-2 ${LEVEL_COLOR[l.level] || ''}`}>
                {l.level.padEnd(7)}
              </span>
              {l.logger_name && (
                <span className='text-muted-foreground mr-2'>{l.logger_name}</span>
              )}
              <span className='whitespace-pre-wrap break-words'>{l.message}</span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

const COMMAND_LABEL: Record<string, string> = {
  restart: '재시작',
  update_now: '코드 업데이트',
  run_diag: '진단 실행',
  retry_task: '태스크 재시도',
  screenshot_now: '스크린샷',
  stop_all_browsers: '브라우저 종료',
  refresh_fingerprint: 'FP 재생성',
  update_adspower_patch: 'AdsPower 패치',
}

function CommandStatus({ status }: { status: string }) {
  const map: Record<string, { color: string; label: string }> = {
    pending: { color: 'text-muted-foreground', label: '대기' },
    delivered: { color: 'text-sky-500', label: '전달됨' },
    completed: { color: 'text-emerald-500', label: '완료' },
    failed: { color: 'text-destructive', label: '실패' },
  }
  const m = map[status] || { color: 'text-muted-foreground', label: status }
  return <span className={`text-xs ${m.color}`}>{m.label}</span>
}

function CommandsTab({ workerId }: { workerId: number }) {
  const [cmds, setCmds] = useState<CommandEntry[]>([])
  const [loading, setLoading] = useState(true)
  // Slice 1 follow-up — 원격 PowerShell 단발 실행 UI.
  const [shellScript, setShellScript] = useState('')
  const [shellTimeout, setShellTimeout] = useState(30)
  const [shellSending, setShellSending] = useState(false)

  const load = async () => {
    try {
      const data = await fetchApi<CommandEntry[]>(
        `/api/admin/workers/${workerId}/commands?limit=50`,
      )
      setCmds(data || [])
    } catch (e) {
      toast.error('명령 이력 로딩 실패', {
        description: e instanceof Error ? e.message : String(e),
      })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    setLoading(true)
    load()
    const id = setInterval(load, 3000)
    return () => clearInterval(id)
  }, [workerId])

  const sendCommand = async (command: string) => {
    try {
      await fetchApi(`/api/admin/workers/${workerId}/command`, {
        method: 'POST',
        body: JSON.stringify({ command }),
      })
      toast.success(`명령 발행: ${COMMAND_LABEL[command] || command}`)
      load()
    } catch (e) {
      toast.error('실패', {
        description: e instanceof Error ? e.message : String(e),
      })
    }
  }

  const sendShell = async () => {
    const script = shellScript.trim()
    if (!script) {
      toast.error('스크립트 비어있음')
      return
    }
    const timeout = Number.isFinite(shellTimeout) ? shellTimeout : 30
    setShellSending(true)
    try {
      await fetchApi(`/api/admin/workers/${workerId}/shell`, {
        method: 'POST',
        body: JSON.stringify({ script, timeout_sec: timeout }),
      })
      toast.success(`shell 발행 (timeout ${timeout}s)`, {
        description: '아래 명령 이력에서 결과 확인',
      })
      setShellScript('')
      load()
    } catch (e) {
      toast.error('shell 발행 실패', {
        description: e instanceof Error ? e.message : String(e),
      })
    } finally {
      setShellSending(false)
    }
  }

  return (
    <div className='flex flex-col h-full gap-3'>
      <div>
        <p className='text-xs text-muted-foreground mb-2'>빠른 명령</p>
        <div className='grid grid-cols-2 gap-1.5'>
          {(['run_diag', 'screenshot_now', 'restart', 'update_now', 'stop_all_browsers', 'refresh_fingerprint'] as const).map(c => (
            <Button
              key={c}
              variant='outline'
              size='sm'
              onClick={() => sendCommand(c)}
              className='justify-start h-8 text-xs'
            >
              <Send className='h-3 w-3 mr-1.5' />
              {COMMAND_LABEL[c] || c}
            </Button>
          ))}
        </div>
      </div>
      <div>
        <p className='text-xs text-muted-foreground mb-2'>원격 PowerShell (단발)</p>
        <Textarea
          placeholder='git rev-parse --short HEAD'
          value={shellScript}
          onChange={(e) => setShellScript(e.target.value)}
          className='text-xs font-mono min-h-[64px]'
          disabled={shellSending}
        />
        <div className='flex items-center gap-2 mt-1.5'>
          <Input
            type='number'
            min={1}
            max={120}
            value={shellTimeout}
            onChange={(e) => setShellTimeout(Number(e.target.value) || 30)}
            className='h-8 w-24 text-xs'
            disabled={shellSending}
          />
          <span className='text-[11px] text-muted-foreground'>sec</span>
          <Button
            size='sm'
            onClick={sendShell}
            disabled={shellSending || !shellScript.trim()}
            className='ml-auto h-8 text-xs'
          >
            <Terminal className='h-3 w-3 mr-1.5' />
            실행
          </Button>
        </div>
      </div>
      <div className='flex-1 min-h-0 overflow-y-auto rounded-md border bg-muted/20'>
        {loading ? (
          <div className='text-muted-foreground text-center py-8 text-xs'>불러오는 중...</div>
        ) : cmds.length === 0 ? (
          <div className='text-muted-foreground text-center py-8 text-xs'>이력 없음</div>
        ) : (
          <div className='divide-y divide-border'>
            {cmds.map(c => (
              <div key={c.id} className='p-2 text-xs'>
                <div className='flex items-center justify-between mb-0.5'>
                  <span className='font-medium'>
                    {COMMAND_LABEL[c.command] || c.command}
                    <span className='text-muted-foreground ml-1.5 font-mono text-[10px]'>#{c.id}</span>
                  </span>
                  <CommandStatus status={c.status} />
                </div>
                <div className='text-muted-foreground text-[11px] flex gap-3 flex-wrap'>
                  <span>발행 {relTime(c.issued_at)}</span>
                  {c.delivered_at && <span>전달 {relTime(c.delivered_at)}</span>}
                  {c.completed_at && <span>완료 {relTime(c.completed_at)}</span>}
                </div>
                {c.error_message && (
                  <p className='text-destructive text-[11px] mt-1'>{c.error_message}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ─────────────── Phase 4 Web Terminal Tab ───────────────

interface TerminalSessionState {
  session_id: number
  session_token: string
  status: string
}

interface TerminalChunkEntry {
  id: number
  stream: 'stdout' | 'stderr'
  seq: number
  data: string
  byte_size: number
  produced_at: string
}

function TerminalTab({
  workerId,
  session,
  setSession,
}: {
  workerId: number
  session: TerminalSessionState | null
  setSession: (s: TerminalSessionState | null) => void
}) {
  // session state 는 WorkerDebugDrawer 가 보관. tab 전환에도 보존.
  // Radix TabsContent 가 inactive 시 children unmount 하므로 lift 필수.
  const [chunks, setChunks] = useState<TerminalChunkEntry[]>([])
  const [totalBytes, setTotalBytes] = useState(0)
  const [maxBytes, setMaxBytes] = useState(10 * 1024 * 1024)
  const [inputText, setInputText] = useState('')
  const [opening, setOpening] = useState(false)
  const [sending, setSending] = useState(false)
  const [interrupting, setInterrupting] = useState(false)
  const [autoScroll, setAutoScroll] = useState(true)
  const lastIdRef = useRef<number>(0)
  const scrollRef = useRef<HTMLDivElement>(null)

  const openTerminal = async () => {
    setOpening(true)
    try {
      const r = await fetchApi<{
        session_id: number
        session_token: string
        status: string
        worker_id: number
      }>(`/api/admin/workers/${workerId}/terminal/open`, {
        method: 'POST',
        body: JSON.stringify({ shell: 'powershell' }),
      })
      setSession({
        session_id: r.session_id,
        session_token: r.session_token,
        status: r.status,
      })
      lastIdRef.current = 0
      setChunks([])
      setTotalBytes(0)
      toast.success('터미널 세션 열림', {
        description: `worker_id=${r.worker_id}, session=${r.session_id}`,
      })
    } catch (e) {
      toast.error('터미널 open 실패', {
        description: e instanceof Error ? e.message : String(e),
      })
    } finally {
      setOpening(false)
    }
  }

  const closeTerminal = async (silent: boolean = false) => {
    if (!session) return
    try {
      await fetchApi(`/api/admin/terminal/${session.session_id}/close`, {
        method: 'POST',
      })
      if (!silent) toast.success('터미널 close 요청')
    } catch (e) {
      if (!silent) {
        toast.error('close 실패', {
          description: e instanceof Error ? e.message : String(e),
        })
      }
    } finally {
      setSession(null)
    }
  }

  const interruptTerminal = async () => {
    if (!session) return
    setInterrupting(true)
    try {
      await fetchApi(`/api/admin/terminal/${session.session_id}/interrupt`, {
        method: 'POST',
      })
      toast.success('interrupt 발행 (process tree kill)')
    } catch (e) {
      toast.error('interrupt 실패', {
        description: e instanceof Error ? e.message : String(e),
      })
    } finally {
      setInterrupting(false)
    }
  }

  const sendInput = async () => {
    if (!session) return
    const data = inputText
    if (!data) return
    setSending(true)
    try {
      // PowerShell 은 Enter 필요. textarea 입력 끝에 \n 보장.
      const payload = data.endsWith('\n') ? data : data + '\n'
      await fetchApi(`/api/admin/terminal/${session.session_id}/input`, {
        method: 'POST',
        body: JSON.stringify({ data: payload }),
      })
      setInputText('')
    } catch (e) {
      toast.error('input 실패', {
        description: e instanceof Error ? e.message : String(e),
      })
    } finally {
      setSending(false)
    }
  }

  // chunks polling
  useEffect(() => {
    if (!session) return
    let cancelled = false
    const poll = async () => {
      if (cancelled || !session) return
      try {
        const r = await fetchApi<{
          chunks: TerminalChunkEntry[]
          session_status: string
          total_bytes: number
          max_total_bytes: number
        }>(`/api/admin/terminal/${session.session_id}/chunks?after_id=${lastIdRef.current}`)
        if (cancelled) return
        if (r.chunks.length > 0) {
          setChunks(prev => [...prev, ...r.chunks].slice(-2000))
          lastIdRef.current = r.chunks[r.chunks.length - 1].id
        }
        setTotalBytes(r.total_bytes)
        setMaxBytes(r.max_total_bytes)
        if (r.session_status !== session.status) {
          setSession({ ...session, status: r.session_status })
        }
        if (['closed', 'timeout', 'failed'].includes(r.session_status)) {
          // server 가 이미 종료 → drawer 측 session 정리
          setSession(null)
        }
      } catch {
        // 무시
      }
    }
    poll()
    const id = setInterval(poll, 800)
    return () => { cancelled = true; clearInterval(id) }
  }, [session?.session_id])

  // autoscroll
  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [chunks, autoScroll])

  // drawer close 시 명시적 close 는 WorkerDebugDrawer 의 onOpenChange 가 처리.
  // tab 전환 시 unmount 돼도 session state 는 부모 (drawer) 가 보존.

  const statusColor: Record<string, string> = {
    pending: 'text-amber-500',
    active: 'text-emerald-500',
    closing: 'text-amber-500',
    closed: 'text-muted-foreground',
    timeout: 'text-orange-500',
    failed: 'text-destructive',
  }

  if (!session) {
    return (
      <div className='flex flex-col h-full gap-3'>
        <div className='rounded-md border border-sky-500/30 bg-sky-500/5 p-3 text-xs flex items-start gap-2'>
          <Terminal className='h-4 w-4 text-sky-500 shrink-0 mt-0.5' />
          <div className='space-y-1'>
            <p className='font-medium text-foreground'>웹 터미널 (Phase 4)</p>
            <p className='text-muted-foreground'>
              admin_agent 워커 PC 의 PowerShell 을 인터랙티브로 연결. 같은 세션에서
              cd / env 유지. 10MB / 4시간 / 15분 idle 자동 종료.
            </p>
          </div>
        </div>
        <Button
          onClick={openTerminal}
          disabled={opening}
          className='w-full'
        >
          <Power className='h-4 w-4 mr-2' />
          {opening ? '세션 여는 중...' : '터미널 세션 열기'}
        </Button>
        <p className='text-[11px] text-muted-foreground'>
          desktop_worker 워커 id 로 발행해도 paired admin_agent 로 자동 라우팅됩니다.
        </p>
      </div>
    )
  }

  return (
    <div className='flex flex-col h-full gap-2'>
      <div className='flex items-center gap-2 flex-wrap'>
        <span className='text-xs text-muted-foreground'>session</span>
        <span className='font-mono text-xs'>#{session.session_id}</span>
        <span className={`text-xs font-medium ${statusColor[session.status] || ''}`}>
          {session.status}
        </span>
        <span className='text-[11px] text-muted-foreground ml-2'>
          {(totalBytes / 1024).toFixed(1)} / {(maxBytes / 1024 / 1024).toFixed(0)} MB
        </span>
        <label className='flex items-center gap-1.5 text-xs text-muted-foreground ml-auto'>
          <input type='checkbox' checked={autoScroll} onChange={e => setAutoScroll(e.target.checked)} />
          자동 스크롤
        </label>
        <Button
          variant='outline'
          size='sm'
          onClick={interruptTerminal}
          disabled={interrupting}
          className='h-7 px-2 text-xs'
        >
          <Zap className='h-3 w-3 mr-1' />
          interrupt
        </Button>
        <Button
          variant='outline'
          size='sm'
          onClick={() => closeTerminal()}
          className='h-7 px-2 text-xs'
        >
          <X className='h-3 w-3 mr-1' />
          close
        </Button>
      </div>
      <div
        ref={scrollRef}
        className='flex-1 min-h-0 overflow-y-auto rounded-md border bg-black/90 p-2 font-mono text-[11px] leading-snug text-green-200'
      >
        {chunks.length === 0 ? (
          <div className='text-muted-foreground/60 text-center py-8'>
            output 대기 중...
          </div>
        ) : (
          chunks.map(c => (
            <span
              key={c.id}
              className={c.stream === 'stderr' ? 'text-red-400 whitespace-pre-wrap' : 'whitespace-pre-wrap'}
            >
              {c.data}
            </span>
          ))
        )}
      </div>
      <div className='flex gap-2'>
        <Textarea
          placeholder='명령 입력 (Enter 자동). Shift+Enter 는 줄바꿈'
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              sendInput()
            }
          }}
          className='text-xs font-mono min-h-[48px] flex-1'
          disabled={sending || session.status !== 'active'}
        />
        <Button
          onClick={sendInput}
          disabled={sending || !inputText || session.status !== 'active'}
          className='self-stretch'
        >
          <Send className='h-3 w-3 mr-1' />
          send
        </Button>
      </div>
      {session.status !== 'active' && (
        <p className='text-[11px] text-amber-500'>
          {session.status === 'pending' ? '워커 spawn 대기 중...' : '세션이 active 가 아니라 입력 불가'}
        </p>
      )}
    </div>
  )
}


export function WorkerDebugDrawer({
  worker,
  open,
  onOpenChange,
  onUpdated,
}: {
  worker: WorkerSummary | null
  open: boolean
  onOpenChange: (v: boolean) => void
  onUpdated?: () => void
}) {
  const [verbose, setVerbose] = useState(false)
  const [toggling, setToggling] = useState(false)
  // Codex frontend follow-up: terminal session state 를 lift.
  // tab 전환에도 session 보존, drawer close 시 명시적 cleanup.
  const [terminalSession, setTerminalSession] = useState<TerminalSessionState | null>(null)
  const sessionRef = useRef<TerminalSessionState | null>(null)
  useEffect(() => {
    sessionRef.current = terminalSession
  }, [terminalSession])

  useEffect(() => {
    if (worker) setVerbose(worker.verbose_mode)
  }, [worker])

  // Codex follow-up: drawer 가 다른 worker 로 바뀌거나 닫힐 때 명시적 close.
  // sessionRef 로 최신 세션 추적 (closure stale 회피).
  const handleOpenChange = (next: boolean) => {
    if (!next && sessionRef.current) {
      const sid = sessionRef.current.session_id
      fetchApi(`/api/admin/terminal/${sid}/close`, { method: 'POST' })
        .catch(() => undefined)
      setTerminalSession(null)
    }
    onOpenChange(next)
  }

  if (!worker) return null

  const toggleVerbose = async (next: boolean) => {
    setToggling(true)
    try {
      await fetchApi(`/api/admin/workers/${worker.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ verbose_mode: next }),
      })
      setVerbose(next)
      toast.success(next ? 'Verbose 모드 ON' : 'Verbose 모드 OFF', {
        description: next
          ? '워커가 다음 heartbeat 부터 INFO+ 로그를 push 합니다 (~10초)'
          : '워커가 다음 heartbeat 부터 INFO 로그 push 를 멈춥니다',
      })
      onUpdated?.()
    } catch (e) {
      toast.error('실패', {
        description: e instanceof Error ? e.message : String(e),
      })
    } finally {
      setToggling(false)
    }
  }

  return (
    <Sheet open={open} onOpenChange={handleOpenChange}>
      <SheetContent className='w-full sm:max-w-2xl flex flex-col gap-4'>
        <SheetHeader className='gap-1'>
          <SheetTitle className='flex items-center gap-2'>
            <Terminal className='h-4 w-4' />
            워커 디버그 — {worker.name}
          </SheetTitle>
          <SheetDescription>
            라이브 로그와 명령 이력을 서버에서 직접 확인합니다.
          </SheetDescription>
        </SheetHeader>

        <div className='flex items-center justify-between rounded-md border bg-card/50 px-3 py-2'>
          <div>
            <p className='text-sm font-medium'>Verbose 모드</p>
            <p className='text-xs text-muted-foreground'>
              켜면 INFO+ 로그가 서버로 push 됨 (보통 OFF, 디버깅 시에만)
            </p>
          </div>
          <Switch checked={verbose} onCheckedChange={toggleVerbose} disabled={toggling} />
        </div>

        <Tabs defaultValue='logs' className='flex-1 min-h-0 flex flex-col'>
          <TabsList className='grid grid-cols-3'>
            <TabsTrigger value='logs'>라이브 로그</TabsTrigger>
            <TabsTrigger value='commands'>명령 이력</TabsTrigger>
            <TabsTrigger value='terminal'>웹 터미널</TabsTrigger>
          </TabsList>
          <TabsContent value='logs' className='flex-1 min-h-0 mt-3'>
            <LogTailTab workerId={worker.id} verbose={verbose} />
          </TabsContent>
          <TabsContent value='commands' className='flex-1 min-h-0 mt-3'>
            <CommandsTab workerId={worker.id} />
          </TabsContent>
          <TabsContent value='terminal' className='flex-1 min-h-0 mt-3'>
            <TerminalTab
              workerId={worker.id}
              session={terminalSession}
              setSession={setTerminalSession}
            />
          </TabsContent>
        </Tabs>
      </SheetContent>
    </Sheet>
  )
}
