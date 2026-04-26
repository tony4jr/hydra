import { useEffect, useState } from 'react'
import { Save } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ContentSection } from '../components/content-section'
import { fetchApi } from '@/lib/api'

interface BehaviorConfig {
  weekly_promo_target: number
  weekly_non_promo_target: number
  daily_max_promo: number
  cooldown_days: number
  session_interval_hours: number
  ghost_cooldown_days: number
  ratio_warmup: number
  ratio_active: number
  ratio_cooldown_return: number
}

const defaultConfig: BehaviorConfig = {
  weekly_promo_target: 20,
  weekly_non_promo_target: 40,
  daily_max_promo: 5,
  cooldown_days: 3,
  session_interval_hours: 4,
  ghost_cooldown_days: 7,
  ratio_warmup: 30,
  ratio_active: 100,
  ratio_cooldown_return: 50,
}

const limitFields: { key: keyof BehaviorConfig; label: string; help: string }[] = [
  { key: 'weekly_promo_target', label: '일주일에 프로모 댓글 몇 개 달까요?', help: '주간 프로모 댓글 목표 수' },
  { key: 'weekly_non_promo_target', label: '비프로모 활동은 얼마나 할까요?', help: '자연스러운 활동을 위한 주간 비프로모 댓글 수' },
  { key: 'daily_max_promo', label: '하루에 프로모 댓글 최대 몇 개?', help: '일일 최대 프로모 댓글 수 (계정 보호)' },
  { key: 'cooldown_days', label: '같은 채널 재방문까지 며칠 기다릴까요?', help: '동일 채널 쿨다운 일수' },
  { key: 'session_interval_hours', label: '세션 사이 최소 몇 시간 대기할까요?', help: '연속 세션 방지를 위한 최소 간격' },
  { key: 'ghost_cooldown_days', label: '고스트 판정 후 며칠 쉴까요?', help: '고스트 감지 후 재활동까지 대기 일수' },
]

export function SettingsBehavior() {
  const [config, setConfig] = useState<BehaviorConfig>(defaultConfig)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    fetchApi<Record<string, string>>('/settings/api/all')
      .then(data => {
        const parsed: Partial<BehaviorConfig> = {}
        for (const [k, v] of Object.entries(data)) {
          if (k in defaultConfig) {
            (parsed as unknown as Record<string, number>)[k] = parseInt(v, 10) || (defaultConfig as unknown as Record<string, number>)[k]
          }
        }
        setConfig(prev => ({ ...prev, ...parsed }))
      })
      .catch(() => {})

    // Load live status_ratios — overrides whatever was in flat keys
    fetchApi<{ ratios: Record<string, number> }>('/settings/api/status-ratios')
      .then(data => {
        if (data?.ratios) {
          setConfig(prev => ({
            ...prev,
            ratio_warmup: Math.round((data.ratios.warmup ?? 0.3) * 100),
            ratio_active: Math.round((data.ratios.active ?? 1.0) * 100),
            ratio_cooldown_return: Math.round((data.ratios.cooldown ?? 0.5) * 100),
          }))
        }
      })
      .catch(() => {})
  }, [])

  const update = (key: keyof BehaviorConfig, value: string) => {
    const num = parseInt(value, 10)
    if (!isNaN(num) && num >= 0) {
      setConfig(prev => ({ ...prev, [key]: num }))
    }
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      // Save flat key-value pairs (legacy format)
      await fetchApi('/settings/api/save', { method: 'POST', body: JSON.stringify(config) })
      // Also save to live status_ratios endpoint (used by account_limits.py)
      const ratios = {
        warmup: config.ratio_warmup / 100,
        active: config.ratio_active / 100,
        cooldown: config.ratio_cooldown_return / 100,
        registered: 0.0,
      }
      await fetchApi('/settings/api/status-ratios', {
        method: 'POST',
        body: JSON.stringify({ ratios }),
      })
      const { toast } = await import('sonner')
      toast.success('저장됨', { description: '한도 비율 즉시 적용' })
    } catch (e) {
      const { toast } = await import('sonner')
      toast.error('저장 실패', { description: e instanceof Error ? e.message : String(e) })
    } finally { setSaving(false) }
  }

  return (
    <ContentSection title='행동 패턴' desc='봇의 작업 빈도, 쿨다운, 세션 간격을 설정합니다.'>
      <div className='space-y-6'>

        {/* 한도 설정 */}
        <div>
          <h3 className='text-foreground font-semibold text-[15px] mb-4'>작업 한도</h3>
          <div className='space-y-5'>
            {limitFields.map(({ key, label, help }) => (
              <div key={key}>
                <label className='text-foreground text-sm font-medium block mb-1'>{label}</label>
                <p className='text-muted-foreground text-xs mb-2'>{help}</p>
                <Input
                  type='number'
                  min={0}
                  value={config[key]}
                  onChange={e => update(key, e.target.value)}
                  className='max-w-[200px]'
                />
              </div>
            ))}
          </div>
        </div>

        {/* 계정 상태별 비율 */}
        <div className='border-t border-border pt-5'>
          <h3 className='text-foreground font-semibold text-[15px] mb-2'>계정 상태별 한도 비율</h3>
          <p className='text-muted-foreground text-xs mb-4'>
            위의 기본 한도에 비율을 곱해서 적용해요. 워밍업 계정은 보수적으로, 안정 계정은 공격적으로.
          </p>

          <div className='space-y-4'>
            <div className='flex items-center gap-4'>
              <div className='w-32'>
                <span className='hydra-tag hydra-tag-warning text-[11px]'>● 워밍업</span>
              </div>
              <div className='flex items-center gap-2'>
                <Input
                  type='number'
                  min={0}
                  max={100}
                  value={config.ratio_warmup}
                  onChange={e => update('ratio_warmup', e.target.value)}
                  className='w-20 text-center'
                />
                <span className='text-muted-foreground text-sm'>%</span>
              </div>
              <span className='text-muted-foreground text-xs'>
                → 하루 최대 {Math.round(config.daily_max_promo * config.ratio_warmup / 100)}개
              </span>
            </div>

            <div className='flex items-center gap-4'>
              <div className='w-32'>
                <span className='hydra-tag hydra-tag-success text-[11px]'>● 활성</span>
              </div>
              <div className='flex items-center gap-2'>
                <Input
                  type='number'
                  min={0}
                  max={200}
                  value={config.ratio_active}
                  onChange={e => update('ratio_active', e.target.value)}
                  className='w-20 text-center'
                />
                <span className='text-muted-foreground text-sm'>%</span>
              </div>
              <span className='text-muted-foreground text-xs'>
                → 하루 최대 {Math.round(config.daily_max_promo * config.ratio_active / 100)}개
              </span>
            </div>

            <div className='flex items-center gap-4'>
              <div className='w-32'>
                <span className='hydra-tag hydra-tag-blue text-[11px]'>● 쿨다운 복귀</span>
              </div>
              <div className='flex items-center gap-2'>
                <Input
                  type='number'
                  min={0}
                  max={100}
                  value={config.ratio_cooldown_return}
                  onChange={e => update('ratio_cooldown_return', e.target.value)}
                  className='w-20 text-center'
                />
                <span className='text-muted-foreground text-sm'>%</span>
              </div>
              <span className='text-muted-foreground text-xs'>
                → 하루 최대 {Math.round(config.daily_max_promo * config.ratio_cooldown_return / 100)}개
              </span>
            </div>
          </div>
        </div>

        <div className='flex justify-end pt-2'>
          <Button onClick={handleSave} disabled={saving} className='hydra-btn-press'>
            <Save className='mr-2 h-4 w-4' />
            {saving ? '저장 중...' : '저장'}
          </Button>
        </div>
      </div>
    </ContentSection>
  )
}
