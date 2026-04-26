/**
 * Fleet View — 계정을 살아있는 카드로 보여주는 함대 모니터.
 *
 * Each card has:
 *   • status accent (left border color)
 *   • live pulse if active
 *   • last action + time
 *   • health score (warmup_day, ghost_count)
 *   • brand-aligned hover lift
 */
import { Cpu, Globe } from 'lucide-react'

interface AccountCard {
  id: number
  gmail: string
  status: string
  warmup_day?: number
  ghost_count?: number
  ipp_flagged?: boolean
  adspower_profile_id?: string | null
  last_active?: string | null
}

const STATUS_LABEL: Record<string, string> = {
  registered: '등록됨',
  warmup: '워밍업',
  active: '활성',
  cooldown: '쿨다운',
  identity_challenge: '본인인증',
  suspended: '정지',
  retired: '퇴역',
  captcha_stuck: '캡차',
  login_failed: '로그인 실패',
  ip_blocked: 'IP 차단',
}

function statusTag(status: string): string {
  if (status === 'active') return 'hydra-tag hydra-tag-success'
  if (status === 'warmup') return 'hydra-tag hydra-tag-warning'
  if (status === 'cooldown') return 'hydra-tag hydra-tag-blue'
  if (['suspended', 'identity_challenge', 'login_failed', 'captcha_stuck', 'ip_blocked'].includes(status)) {
    return 'hydra-tag hydra-tag-danger'
  }
  return 'hydra-tag hydra-tag-muted'
}

function shortGmail(g?: string): string {
  if (!g) return '-'
  return g.split('@')[0].slice(0, 18)
}

interface FleetViewProps {
  accounts: AccountCard[]
  onClick?: (id: number) => void
}

export function FleetView({ accounts, onClick }: FleetViewProps) {
  if (!accounts || accounts.length === 0) {
    return (
      <div className='hydra-empty mt-4'>
        <div className='hydra-empty-icon'>📡</div>
        <div className='hydra-empty-title'>표시할 계정이 없어요</div>
        <div className='hydra-empty-desc'>위에서 계정을 등록하거나 필터를 바꿔보세요.</div>
      </div>
    )
  }

  return (
    <div className='grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 mt-4'>
      {accounts.map(a => {
        const isAlive = a.status === 'active'
        return (
          <div
            key={a.id}
            data-status={a.status}
            className='hydra-fleet-card'
            onClick={() => onClick?.(a.id)}
            role='button'
            tabIndex={0}
          >
            <div className='flex items-center justify-between'>
              <div className='hydra-fleet-name'>
                {isAlive && <span className='hydra-fleet-pulse' />}
                {shortGmail(a.gmail)}
              </div>
              <span className={statusTag(a.status)}>
                {STATUS_LABEL[a.status] || a.status}
              </span>
            </div>

            <div className='hydra-fleet-meta'>
              {a.adspower_profile_id && (
                <span className='inline-flex items-center gap-1'>
                  <Cpu className='size-3' />
                  {a.adspower_profile_id}
                </span>
              )}
              {(a.warmup_day || 0) > 0 && (
                <span>워밍업 D{a.warmup_day}</span>
              )}
              {(a.ghost_count || 0) > 0 && (
                <span className='text-rose-500'>👻 {a.ghost_count}</span>
              )}
              {a.ipp_flagged && (
                <span className='text-amber-500'>⚠ IPP</span>
              )}
            </div>

            {a.last_active && (
              <div className='text-[11px] text-muted-foreground/60'>
                <Globe className='inline size-3 mr-1 -mt-0.5' />
                {a.last_active}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
