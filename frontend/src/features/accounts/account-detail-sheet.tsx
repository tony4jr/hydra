import { useEffect, useState } from 'react'
import { ShieldCheck, ShieldAlert, UserCheck, RefreshCcw, Link2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import {
  Sheet, SheetContent, SheetHeader, SheetTitle,
} from '@/components/ui/sheet'
import { fetchApi } from '@/lib/api'

interface AccountDetail {
  id: number
  gmail: string
  status: string
  warmup_group: string | null
  warmup_day: number
  warmup_start_date: string | null
  warmup_end_date: string | null
  onboard_completed_at: string | null
  ghost_count: number
  persona: string | null  // JSON string
  adspower_profile_id: string | null
  youtube_channel_id: string | null
  has_cookies: boolean
  has_totp: boolean
  identity_challenge_until: string | null
  identity_challenge_count: number
  notes: string | null
  created_at: string
  last_active_at: string | null
  daily_comment_limit: number
  daily_like_limit: number
  weekly_comment_limit: number
  weekly_like_limit: number
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

interface OnboardActionsEntry {
  task_id: number
  status: string
  created_at: string
  completed_at: string | null
  error: string | null
  actions: string[]
  critical_failures: string[]
  ok: boolean | null
}

interface ChannelVerify {
  channel_id: string
  live_name: string | null
  expected_name: string | null
  match: boolean
}

interface AccountDetailSheetProps {
  accountId: number | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

const statusLabels: Record<string, string> = {
  active: '활성', warmup: '워밍업', cooldown: '쿨다운',
  retired: '정지', ghost: '고스트', registered: '등록됨',
  profile_set: '프로필 설정', identity_challenge: '본인 인증',
  suspended: '영구 정지',
}
const statusTagClass: Record<string, string> = {
  active: 'hydra-tag-success', warmup: 'hydra-tag-warning', cooldown: 'hydra-tag-blue',
  retired: 'hydra-tag-danger', ghost: 'hydra-tag-ghost', registered: 'hydra-tag-muted',
  profile_set: 'hydra-tag-muted', identity_challenge: 'hydra-tag-danger',
  suspended: 'hydra-tag-danger',
}

const warmupGroupDays: Record<string, number> = { A: 2, B: 3, C: 7, D: 14, E: 21 }

const statusTransitions = ['registered', 'profile_set', 'warmup', 'active', 'cooldown', 'retired'] as const

function formatCountdown(until: string | null): string {
  if (!until) return ''
  const ms = new Date(until).getTime() - Date.now()
  if (ms <= 0) return '만료'
  const d = Math.floor(ms / 86400000)
  const h = Math.floor((ms % 86400000) / 3600000)
  return d > 0 ? `D-${d} (${h}h)` : `${h}h`
}

export function AccountDetailSheet({ accountId, open, onOpenChange }: AccountDetailSheetProps) {
  const [detail, setDetail] = useState<AccountDetail | null>(null)
  const [metrics, setMetrics] = useState<AccountMetrics | null>(null)
  const [history, setHistory] = useState<ActivityEntry[]>([])
  const [onboardActions, setOnboardActions] = useState<OnboardActionsEntry[]>([])
  const [channelVerify, setChannelVerify] = useState<ChannelVerify | null>(null)
  const [actioning, setActioning] = useState(false)
  const [actionMsg, setActionMsg] = useState('')

  const reload = () => {
    if (!accountId) return
    fetchApi<AccountDetail>(`/accounts/api/${accountId}`).then(setDetail).catch(() => {})
  }

  useEffect(() => {
    if (!accountId || !open) return
    setDetail(null); setMetrics(null); setHistory([]); setOnboardActions([]); setChannelVerify(null); setActionMsg('')

    fetchApi<AccountDetail>(`/accounts/api/${accountId}`).then(setDetail).catch(() => {})
    fetchApi<AccountMetrics>(`/accounts/api/${accountId}/metrics`).then(setMetrics).catch(() => {})
    fetchApi<{ items: ActivityEntry[] }>(`/accounts/api/${accountId}/history`)
      .then(d => setHistory(d.items || [])).catch(() => {})
    fetchApi<{ items: OnboardActionsEntry[] }>(`/accounts/api/${accountId}/onboard/actions`)
      .then(d => setOnboardActions(d.items || [])).catch(() => {})
  }, [accountId, open])

  const call = async (path: string, method = 'POST', body?: object, successMsg = '완료') => {
    if (!accountId) return
    setActioning(true); setActionMsg('')
    try {
      await fetchApi(path, { method, body: body ? JSON.stringify(body) : undefined })
      setActionMsg(successMsg)
      reload()
    } catch (e: unknown) {
      setActionMsg(`실패: ${e instanceof Error ? e.message : 'unknown'}`)
    } finally { setActioning(false) }
  }

  const changeStatus = (s: string) =>
    call(`/accounts/api/${accountId}/status?status=${s}`, 'POST', undefined, `상태 → ${statusLabels[s] || s}`)

  const unlockIdentity = () =>
    call(`/accounts/api/${accountId}/identity-challenge/unlock`, 'POST', undefined, '본인 인증 쿨다운 해제')

  const banIdentity = () =>
    call(`/accounts/api/${accountId}/identity-challenge/ban`, 'POST', undefined, '영구 정지 처리')

  const retryOnboard = () =>
    call(`/accounts/api/${accountId}/onboard/retry`, 'POST', undefined, '온보딩 재시도 큐잉')

  const verifyChannel = async () => {
    if (!accountId) return
    setActioning(true); setActionMsg('')
    try {
      const r = await fetchApi<ChannelVerify>(`/accounts/api/${accountId}/channel/verify`)
      setChannelVerify(r)
    } catch { setActionMsg('채널 검증 실패') }
    finally { setActioning(false) }
  }

  const persona = (() => {
    try { return detail?.persona ? JSON.parse(detail.persona) : null }
    catch { return null }
  })()

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className='overflow-y-auto sm:max-w-lg'>
        <SheetHeader>
          <SheetTitle>{persona?.name || detail?.gmail || '계정 상세'}</SheetTitle>
        </SheetHeader>

        {detail ? (
          <div className='space-y-5 px-4 pb-4'>
            {/* Info */}
            <section>
              <h4 className='text-foreground font-semibold text-[14px] mb-3'>계정 정보</h4>
              <div className='space-y-2 text-[13px]'>
                <Row label='이메일' value={detail.gmail} />
                <Row label='상태'>
                  <span className={`hydra-tag ${statusTagClass[detail.status] || 'hydra-tag-muted'}`}>
                    {statusLabels[detail.status] || detail.status}
                  </span>
                </Row>
                <Row label='AdsPower 프로필' value={detail.adspower_profile_id || '-'} mono />
                <Row label='페르소나' value={persona?.name || '-'} />
                <Row label='생성일' value={new Date(detail.created_at).toLocaleDateString('ko')} />
                <Row label='마지막 활동' value={detail.last_active_at ? new Date(detail.last_active_at).toLocaleString('ko') : '-'} />
              </div>
            </section>

            <Separator />

            {/* Onboarding */}
            <section>
              <h4 className='text-foreground font-semibold text-[14px] mb-3 flex items-center gap-2'>
                <UserCheck className='h-4 w-4' /> 온보딩
              </h4>
              <div className='space-y-2 text-[13px]'>
                <Row label='완료 시각' value={detail.onboard_completed_at ? new Date(detail.onboard_completed_at).toLocaleString('ko') : '미완료'} />
                <Row label='쿠키' value={detail.has_cookies ? '있음' : '없음'} />
              </div>
              {onboardActions.length > 0 && (
                <div className='mt-3 space-y-2'>
                  <p className='text-muted-foreground text-[12px]'>최근 시도</p>
                  {onboardActions.slice(0, 3).map(o => (
                    <div key={o.task_id} className='bg-background border border-border/50 rounded-lg p-2.5 text-[12px]'>
                      <div className='flex justify-between mb-1'>
                        <span className={o.ok === false ? 'text-destructive' : 'text-foreground'}>
                          #{o.task_id} · {o.status}
                        </span>
                        <span className='text-muted-foreground'>{new Date(o.created_at).toLocaleString('ko')}</span>
                      </div>
                      {o.actions.length > 0 && (
                        <div className='flex flex-wrap gap-1 mt-1'>
                          {o.actions.map((a, i) => (
                            <span key={i} className='hydra-tag hydra-tag-muted text-[11px]'>{a}</span>
                          ))}
                        </div>
                      )}
                      {o.critical_failures.length > 0 && (
                        <div className='flex flex-wrap gap-1 mt-1'>
                          {o.critical_failures.map((f, i) => (
                            <span key={i} className='hydra-tag hydra-tag-danger text-[11px]'>{f}</span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
              <Button size='sm' variant='outline' className='mt-3 w-full' disabled={actioning} onClick={retryOnboard}>
                <RefreshCcw className='h-3.5 w-3.5 mr-1' /> 온보딩 재시도
              </Button>
            </section>

            <Separator />

            {/* 2FA */}
            <section>
              <h4 className='text-foreground font-semibold text-[14px] mb-3 flex items-center gap-2'>
                <ShieldCheck className='h-4 w-4' /> 2FA / OTP
              </h4>
              <div className='space-y-2 text-[13px]'>
                <Row label='TOTP 시크릿' value={detail.has_totp ? '등록됨' : '없음'} />
                <Row label='2FA 활성화' value={detail.has_totp ? '부분 (시크릿만)' : '비활성화'} />
              </div>
              <p className='text-muted-foreground text-[11px] mt-2'>
                2FA 완전 활성화는 전화번호/패스키 필요. 시크릿만으로 도전 대응 가능.
              </p>
            </section>

            <Separator />

            {/* Warmup */}
            <section>
              <h4 className='text-foreground font-semibold text-[14px] mb-3'>워밍업</h4>
              <div className='space-y-2 text-[13px]'>
                <Row label='그룹' value={detail.warmup_group || '-'} />
                <Row label='진행도' value={
                  detail.warmup_group
                    ? `Day ${detail.warmup_day}/${warmupGroupDays[detail.warmup_group] || '?'}`
                    : '-'
                } />
                <Row label='시작' value={detail.warmup_start_date ? new Date(detail.warmup_start_date).toLocaleDateString('ko') : '-'} />
                <Row label='종료' value={detail.warmup_end_date ? new Date(detail.warmup_end_date).toLocaleDateString('ko') : '-'} />
              </div>
            </section>

            <Separator />

            {/* Identity Challenge */}
            {(detail.identity_challenge_count > 0 || detail.status === 'identity_challenge') && (
              <>
                <section>
                  <h4 className='text-foreground font-semibold text-[14px] mb-3 flex items-center gap-2'>
                    <ShieldAlert className='h-4 w-4 text-rose-500' /> 본인 인증
                  </h4>
                  <div className='space-y-2 text-[13px]'>
                    <Row label='발생 횟수' value={`${detail.identity_challenge_count}회`} />
                    <Row label='쿨다운 해제' value={
                      detail.identity_challenge_until
                        ? `${new Date(detail.identity_challenge_until).toLocaleString('ko')} (${formatCountdown(detail.identity_challenge_until)})`
                        : '없음'
                    } />
                  </div>
                  <div className='flex gap-2 mt-3'>
                    <Button size='sm' variant='outline' disabled={actioning} onClick={unlockIdentity}>
                      강제 해제
                    </Button>
                    <Button size='sm' variant='destructive' disabled={actioning} onClick={banIdentity}>
                      영구 정지
                    </Button>
                  </div>
                </section>
                <Separator />
              </>
            )}

            {/* Channel */}
            <section>
              <h4 className='text-foreground font-semibold text-[14px] mb-3 flex items-center gap-2'>
                <Link2 className='h-4 w-4' /> 채널
              </h4>
              <div className='space-y-2 text-[13px]'>
                <Row label='채널 ID' value={detail.youtube_channel_id || '-'} mono />
                <Row label='계획된 이름' value={persona?.channel_plan?.title || '-'} />
                <Row label='핸들' value={persona?.channel_plan?.handle ? `@${persona.channel_plan.handle}` : '-'} />
              </div>
              <Button size='sm' variant='outline' className='mt-3 w-full' disabled={actioning || !detail.youtube_channel_id} onClick={verifyChannel}>
                YT 라이브 검증
              </Button>
              {channelVerify && (
                <div className={`mt-2 rounded-lg border p-2.5 text-[12px] ${channelVerify.match ? 'border-green-500/30 bg-green-500/5' : 'border-destructive/30 bg-destructive/5'}`}>
                  <div>실제: <span className='font-mono'>{channelVerify.live_name || '(추출 실패)'}</span></div>
                  <div>기대: <span className='font-mono'>{channelVerify.expected_name || '-'}</span></div>
                  <div className='mt-1'>
                    {channelVerify.match ? '✓ 일치' : '✗ 불일치 — rename 재시도 필요'}
                  </div>
                </div>
              )}
            </section>

            <Separator />

            {/* Persona anti-detect */}
            {persona && (
              <>
                <section>
                  <h4 className='text-foreground font-semibold text-[14px] mb-3'>페르소나 안티디텍션</h4>
                  <div className='space-y-2 text-[13px]'>
                    <Row label='나이/성별' value={`${persona.age}세 ${persona.gender === 'male' ? '남' : '여'}`} />
                    <Row label='지역' value={persona.region || '-'} />
                    <Row label='세션 속도' value={`×${persona.speed_multiplier ?? '?'}`} />
                    <Row label='타이핑' value={persona.typing_style === 'typist' ? '한글자씩' : persona.typing_style === 'paster' ? '붙여넣기' : '?'} />
                    <Row label='활동량' value={`×${persona.activity_multiplier ?? '?'}`} />
                  </div>
                </section>
                <Separator />
              </>
            )}

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
                <div className='hydra-skeleton h-20 rounded-lg' />
              )}
            </section>

            <Separator />

            {/* Limits */}
            <section>
              <h4 className='text-foreground font-semibold text-[14px] mb-3'>한도</h4>
              <div className='space-y-2 text-[13px]'>
                <Row label='일일 댓글' value={`${detail.daily_comment_limit}회`} />
                <Row label='일일 좋아요' value={`${detail.daily_like_limit}회`} />
                <Row label='주간 댓글' value={`${detail.weekly_comment_limit}회`} />
                <Row label='주간 좋아요' value={`${detail.weekly_like_limit}회`} />
              </div>
            </section>

            <Separator />

            {/* Status Transition */}
            <section>
              <h4 className='text-foreground font-semibold text-[14px] mb-3'>상태 수동 전이</h4>
              <div className='flex flex-wrap gap-2'>
                {statusTransitions.map(s => (
                  <Button
                    key={s}
                    size='sm'
                    variant={detail.status === s ? 'default' : 'outline'}
                    disabled={detail.status === s || actioning}
                    onClick={() => changeStatus(s)}
                  >
                    {statusLabels[s] || s}
                  </Button>
                ))}
              </div>
            </section>

            {actionMsg && (
              <p className='text-[12px] text-muted-foreground'>{actionMsg}</p>
            )}

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

function Row({ label, value, mono, children }: {
  label: string; value?: React.ReactNode; mono?: boolean; children?: React.ReactNode
}) {
  return (
    <div className='flex justify-between'>
      <span className='text-muted-foreground'>{label}</span>
      {children || <span className={mono ? 'font-mono text-[12px]' : ''}>{value}</span>}
    </div>
  )
}
