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
}

const defaultConfig: BehaviorConfig = {
  weekly_promo_target: 20,
  weekly_non_promo_target: 40,
  daily_max_promo: 5,
  cooldown_days: 3,
  session_interval_hours: 4,
  ghost_cooldown_days: 7,
}

const fields: { key: keyof BehaviorConfig; label: string; help: string }[] = [
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
    fetchApi<{ settings: Partial<BehaviorConfig> }>('/settings/api/all')
      .then(data => { if (data.settings) setConfig(prev => ({ ...prev, ...data.settings })) })
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
      await fetchApi('/settings/api/save', { method: 'POST', body: JSON.stringify(config) })
    } catch { /* error */ }
    finally { setSaving(false) }
  }

  return (
    <ContentSection title='행동 패턴' desc='봇의 작업 빈도, 쿨다운, 세션 간격을 설정합니다.'>
      <div className='space-y-5'>
        {fields.map(({ key, label, help }) => (
          <div key={key} className='mb-5'>
            <label className='text-foreground text-sm font-medium mb-1.5'>{label}</label>
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
