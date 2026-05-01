/**
 * 메시지 탭 (PR-4d). spec PR-4 §3.
 *
 * core_message / tone_guide / target_audience / mention_rules / personas (max 10).
 */
import { useState } from 'react'

import { useNicheMessaging } from '@/hooks/use-messaging'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'

interface Props {
  nicheId: string
}

export function MessagingTab({ nicheId }: Props) {
  const { messaging, loading, update, addPersona, removePersona } =
    useNicheMessaging(nicheId)

  if (loading) {
    return <Skeleton className='h-64 rounded-xl' />
  }
  if (!messaging) {
    return (
      <div className='bg-card border border-border rounded-xl py-16 text-center'>
        <p className='text-muted-foreground text-[14px]'>메시지 정보를 불러오지 못했어요</p>
      </div>
    )
  }

  return (
    <div className='space-y-5'>
      <CoreFields messaging={messaging} update={update} />
      <PersonaList
        personas={messaging.personas}
        onAdd={addPersona}
        onRemove={removePersona}
      />
    </div>
  )
}

function CoreFields({
  messaging,
  update,
}: {
  messaging: ReturnType<typeof useNicheMessaging>['messaging']
  update: ReturnType<typeof useNicheMessaging>['update']
}) {
  const [core, setCore] = useState(messaging?.core_message ?? '')
  const [tone, setTone] = useState(messaging?.tone_guide ?? '')
  const [audience, setAudience] = useState(messaging?.target_audience ?? '')
  const [mention, setMention] = useState(messaging?.mention_rules ?? '')
  const [saving, setSaving] = useState(false)

  const save = async () => {
    setSaving(true)
    try {
      await update({
        core_message: core,
        tone_guide: tone,
        target_audience: audience,
        mention_rules: mention,
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className='bg-card border border-border rounded-xl p-5 space-y-4'>
      <p className='text-muted-foreground text-[12px]'>핵심 메시지</p>
      <Field label='핵심 메시지' value={core} onChange={setCore} multiline />
      <Field label='톤 가이드' value={tone} onChange={setTone} multiline />
      <Field label='타겟 오디언스' value={audience} onChange={setAudience} />
      <Field label='언급 규칙' value={mention} onChange={setMention} multiline />
      <div className='flex justify-end'>
        <Button onClick={save} disabled={saving} className='hydra-btn-press'>
          {saving ? '저장 중…' : '저장'}
        </Button>
      </div>
    </div>
  )
}

function Field({
  label,
  value,
  onChange,
  multiline,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  multiline?: boolean
}) {
  return (
    <div>
      <label className='block text-foreground text-[13px] mb-1'>{label}</label>
      {multiline ? (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          rows={3}
          className='w-full bg-background border border-border rounded-md text-[13px] px-2 py-1.5'
        />
      ) : (
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className='w-full bg-background border border-border rounded-md text-[13px] px-2 py-1.5'
        />
      )}
    </div>
  )
}

function PersonaList({
  personas,
  onAdd,
  onRemove,
}: {
  personas: ReturnType<typeof useNicheMessaging>['messaging'] extends infer T
    ? T extends { personas: infer P }
      ? P
      : never
    : never
  onAdd: ReturnType<typeof useNicheMessaging>['addPersona']
  onRemove: ReturnType<typeof useNicheMessaging>['removePersona']
}) {
  const [name, setName] = useState('')
  const [weight, setWeight] = useState(50)

  const handleAdd = async () => {
    if (!name.trim()) return
    await onAdd({
      id: crypto.randomUUID(),
      name: name.trim(),
      weight,
    })
    setName('')
    setWeight(50)
  }

  const list = personas as { id: string; name: string; weight: number }[]

  return (
    <div className='bg-card border border-border rounded-xl p-5'>
      <div className='flex items-center justify-between mb-3'>
        <p className='text-muted-foreground text-[12px]'>
          페르소나 ({list.length}/10)
        </p>
      </div>
      {list.length === 0 ? (
        <p className='text-muted-foreground/60 text-[13px] mb-3'>등록된 페르소나가 없어요</p>
      ) : (
        <ul className='divide-y divide-border mb-3'>
          {list.map((p) => (
            <li key={p.id} className='py-2 flex items-center justify-between gap-3'>
              <div className='min-w-0'>
                <p className='text-foreground text-[14px] font-medium truncate'>{p.name}</p>
                <p className='text-muted-foreground/70 text-[11px]'>비율 {p.weight}</p>
              </div>
              <Button variant='ghost' size='sm' onClick={() => onRemove(p.id)}>
                삭제
              </Button>
            </li>
          ))}
        </ul>
      )}
      {list.length < 10 && (
        <div className='flex items-center gap-2 pt-3 border-t border-border'>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder='페르소나 이름'
            className='flex-1 bg-background border border-border rounded-md text-[13px] px-2 py-1.5'
          />
          <input
            type='number'
            value={weight}
            onChange={(e) => setWeight(Number(e.target.value) || 1)}
            min={1}
            max={100}
            className='w-20 bg-background border border-border rounded-md text-[13px] px-2 py-1.5'
          />
          <Button onClick={handleAdd} size='sm' className='hydra-btn-press'>
            추가
          </Button>
        </div>
      )}
    </div>
  )
}
