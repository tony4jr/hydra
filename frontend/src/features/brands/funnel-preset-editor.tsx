/**
 * T18 — 브랜드별 퍼널 단계 프리셋 편집기.
 *
 * 4단계 (인지/고려/전환/리텐션) 의 프롬프트 톤 가이드를 보여주고
 * 미리보기 기능 제공 (Claude key 있으면 실 호출, 없으면 stub).
 */
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { fetchApi } from '@/lib/api'
import { toast } from 'sonner'

interface FunnelStageInfo {
  key: string
  label: string
  description: string
  defaultGuide: string
}

const STAGES: FunnelStageInfo[] = [
  {
    key: 'awareness',
    label: '인지',
    description: '화두 던지기. 브랜드 직접 언급 X.',
    defaultGuide: '영상 주제에 대한 본인 경험/고민을 자연스럽게. 브랜드 직접 언급 금지. 호기심만 유발.',
  },
  {
    key: 'consideration',
    label: '고려',
    description: '비교/검토. 우회 멘션.',
    defaultGuide: '"뭐 드세요?", "효과 있어요?" 같은 질문 또는 "OO 성분 들어간 거 써봤는데" 우회 멘션. 직접 광고 X.',
  },
  {
    key: 'conversion',
    label: '전환',
    description: '구체적 사용 경험.',
    defaultGuide: '구체적 사용 경험 + 효과 짧게. 성분명/방법명 OK, 브랜드명은 mention_rules 따라. 강요 X.',
  },
  {
    key: 'retention',
    label: '리텐션',
    description: '장기 사용자 톤.',
    defaultGuide: '"저도 1년째 써요", "계속 만족" 같은 장기 사용자 톤. 초보자에게 답하듯 정보 공유.',
  },
]

interface Brand {
  id: number
  name: string
  tone_guide?: string
}

interface Props {
  brand: Brand
  onClose?: () => void
}

export function FunnelPresetEditor({ brand }: Props) {
  // brand.tone_guide JSON: { awareness: "...", consideration: "...", ... }
  const initialOverrides: Record<string, string> = {}
  try {
    if (brand.tone_guide) {
      const parsed = JSON.parse(brand.tone_guide)
      if (typeof parsed === 'object' && parsed) {
        Object.assign(initialOverrides, parsed)
      }
    }
  } catch {
    // tone_guide 가 plain text 면 모든 단계에 동일 가이드 적용
    if (brand.tone_guide) {
      STAGES.forEach((s) => {
        initialOverrides[s.key] = brand.tone_guide!
      })
    }
  }

  const [overrides, setOverrides] = useState<Record<string, string>>(initialOverrides)
  const [activeStage, setActiveStage] = useState('awareness')
  const [previews, setPreviews] = useState<Record<string, string[]>>({})
  const [previewing, setPreviewing] = useState(false)

  const setStageGuide = (key: string, value: string) => {
    setOverrides((prev) => ({ ...prev, [key]: value }))
  }

  const reset = (key: string) => {
    setOverrides((prev) => {
      const next = { ...prev }
      delete next[key]
      return next
    })
  }

  const save = async () => {
    try {
      const tone_guide_json = JSON.stringify(overrides)
      await fetchApi(`/brands/${brand.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ tone_guide: tone_guide_json }),
        headers: { 'Content-Type': 'application/json' },
      })
      toast.success('저장됨', {
        description: `${Object.keys(overrides).length}개 단계 톤 가이드 적용.`,
      })
    } catch (e) {
      toast.error('저장 실패', {
        description: e instanceof Error ? e.message : String(e),
      })
    }
  }

  const previewStage = async (stage: string) => {
    setPreviewing(true)
    try {
      // AI sample preview API — Claude key 있으면 실 호출, 없으면 stub 응답
      const samples = await fetchApi<string[]>(`/brands/${brand.id}/preview-comments`, {
        method: 'POST',
        body: JSON.stringify({ funnel_stage: stage, count: 3 }),
        headers: { 'Content-Type': 'application/json' },
      })
      setPreviews((prev) => ({ ...prev, [stage]: samples }))
    } catch (e) {
      toast.error('미리보기 실패', {
        description: 'Claude API key 미설정 또는 백엔드 미구현일 수 있음.',
      })
      // Fallback: 단계별 기본 가이드 보여주기
      setPreviews((prev) => ({
        ...prev,
        [stage]: [
          `(샘플 1 — ${stage} 톤)`,
          `(샘플 2 — ${stage} 톤)`,
          `(샘플 3 — ${stage} 톤)`,
        ],
      }))
    } finally {
      setPreviewing(false)
    }
  }

  return (
    <div className='space-y-4'>
      <div>
        <h3 className='text-lg font-semibold'>{brand.name} — 퍼널 프리셋</h3>
        <p className='text-muted-foreground text-sm'>
          단계별 댓글 톤 가이드. 비워두면 전역 기본값 사용.
        </p>
      </div>

      <Tabs value={activeStage} onValueChange={setActiveStage}>
        <TabsList className='grid w-full grid-cols-4'>
          {STAGES.map((s) => (
            <TabsTrigger key={s.key} value={s.key}>
              {s.label}
              {overrides[s.key] && (
                <Badge variant='outline' className='ml-2 h-4 px-1 text-[10px]'>
                  ✓
                </Badge>
              )}
            </TabsTrigger>
          ))}
        </TabsList>

        {STAGES.map((s) => (
          <TabsContent key={s.key} value={s.key} className='space-y-3'>
            <div>
              <div className='text-muted-foreground text-xs'>설명</div>
              <p className='text-sm'>{s.description}</p>
            </div>

            <div>
              <div className='text-muted-foreground mb-1 text-xs'>기본 가이드</div>
              <div className='bg-muted/30 rounded p-2 text-xs'>{s.defaultGuide}</div>
            </div>

            <div>
              <div className='text-muted-foreground mb-1 text-xs'>
                Override (이 브랜드 전용 — 비워두면 기본값 사용)
              </div>
              <Textarea
                value={overrides[s.key] || ''}
                onChange={(e) => setStageGuide(s.key, e.target.value)}
                placeholder={`(${s.defaultGuide.slice(0, 50)}...)`}
                rows={4}
              />
              {overrides[s.key] && (
                <Button
                  size='sm'
                  variant='ghost'
                  onClick={() => reset(s.key)}
                  className='mt-1'
                >
                  기본값으로 되돌리기
                </Button>
              )}
            </div>

            <div className='flex gap-2'>
              <Button
                size='sm'
                variant='outline'
                onClick={() => previewStage(s.key)}
                disabled={previewing}
              >
                미리보기 (3건)
              </Button>
            </div>

            {previews[s.key] && (
              <div className='space-y-1'>
                <div className='text-muted-foreground text-xs'>샘플</div>
                {previews[s.key].map((p, i) => (
                  <div key={i} className='bg-muted/30 rounded p-2 text-sm font-mono'>
                    {p}
                  </div>
                ))}
              </div>
            )}
          </TabsContent>
        ))}
      </Tabs>

      <div className='flex justify-end gap-2 border-t pt-3'>
        <Button onClick={save}>저장</Button>
      </div>
    </div>
  )
}
