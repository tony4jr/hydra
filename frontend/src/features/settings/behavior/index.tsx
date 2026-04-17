import { useEffect, useState } from 'react'
import { Save } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
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

const configLabels: Record<keyof BehaviorConfig, { label: string; desc: string }> = {
  weekly_promo_target: {
    label: '주간 프로모 댓글 목표',
    desc: '일주일간 작성할 프로모 댓글 수',
  },
  weekly_non_promo_target: {
    label: '주간 비프로모 활동 목표',
    desc: '자연스러운 활동을 위한 비프로모 댓글 수',
  },
  daily_max_promo: {
    label: '일일 최대 프로모',
    desc: '하루에 작성할 최대 프로모 댓글 수',
  },
  cooldown_days: {
    label: '쿨다운 일수',
    desc: '같은 채널에 다시 댓글 달기까지 대기 일수',
  },
  session_interval_hours: {
    label: '세션 간격 (시간)',
    desc: '세션 사이 최소 대기 시간',
  },
  ghost_cooldown_days: {
    label: '고스트 쿨다운 일수',
    desc: '고스트 판정 후 재활동까지 대기 일수',
  },
}

export function SettingsBehavior() {
  const [config, setConfig] = useState<BehaviorConfig>(defaultConfig)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    fetchApi<{ settings: Partial<BehaviorConfig> }>('/settings/api/all')
      .then((data) => {
        if (data.settings) {
          setConfig((prev) => ({ ...prev, ...data.settings }))
        }
      })
      .catch(() => {})
  }, [])

  const update = (key: keyof BehaviorConfig, value: string) => {
    const num = parseInt(value, 10)
    if (!isNaN(num) && num >= 0) {
      setConfig((prev) => ({ ...prev, [key]: num }))
    }
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await fetchApi('/settings/api/save', {
        method: 'POST',
        body: JSON.stringify(config),
      })
    } catch {
      alert('저장 실패')
    } finally {
      setSaving(false)
    }
  }

  return (
    <ContentSection
      title='행동 패턴'
      desc='댓글 작성 빈도, 쿨다운, 세션 간격 등 봇 행동 패턴을 설정합니다.'
    >
      <div className='space-y-6'>
        {(Object.keys(configLabels) as (keyof BehaviorConfig)[]).map((key) => (
          <div key={key} className='space-y-1'>
            <Label htmlFor={key}>{configLabels[key].label}</Label>
            <Input
              id={key}
              type='number'
              min={0}
              value={config[key]}
              onChange={(e) => update(key, e.target.value)}
              className='max-w-[200px]'
            />
            <p className='text-xs text-muted-foreground'>
              {configLabels[key].desc}
            </p>
          </div>
        ))}

        <div className='flex justify-end'>
          <Button onClick={handleSave} disabled={saving}>
            <Save className='mr-2 h-4 w-4' />
            {saving ? '저장 중...' : '저장'}
          </Button>
        </div>
      </div>
    </ContentSection>
  )
}
