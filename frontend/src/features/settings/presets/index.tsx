import { useEffect, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ContentSection } from '../components/content-section'
import { fetchApi } from '@/lib/api'

interface PresetStep {
  step_number: number
  role: string
  type: string
  tone: string
  target: string
  like_count: number
  delay_min: number
  delay_max: number
}

interface Preset {
  id: number
  code: string
  name: string
  description: string
  is_system: boolean
  steps: PresetStep[]
}

const roleLabels: Record<string, string> = {
  seed: '시드', asker: '질문자', witness: '목격자', agree: '동조자',
  curious: '궁금이', info: '정보통', fan: '팬', qa: 'QA', supporter: '서포터',
}
const roleColors: Record<string, string> = {
  seed: '#6c5ce7', asker: '#3b82f6', witness: '#22c55e', agree: '#eab308',
  curious: '#f97316', info: '#ef4444', fan: '#ec4899', qa: '#8b5cf6', supporter: '#06b6d4',
}
const typeLabels: Record<string, string> = { comment: '댓글', reply: '대댓글' }
const roles = ['seed', 'asker', 'witness', 'agree', 'curious', 'info', 'fan', 'qa', 'supporter']
const types = ['comment', 'reply']

const defaultStep: PresetStep = {
  step_number: 1, role: 'seed', type: 'comment', tone: '', target: 'video', like_count: 0, delay_min: 5, delay_max: 25,
}

export function SettingsPresets() {
  const [presets, setPresets] = useState<Preset[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)

  // Edit step modal
  const [editStepIdx, setEditStepIdx] = useState<number | null>(null)
  const [editStepData, setEditStepData] = useState<PresetStep>(defaultStep)

  // Create new preset
  const [createOpen, setCreateOpen] = useState(false)
  const [newCode, setNewCode] = useState('')
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')

  const [saving, setSaving] = useState(false)

  const loadPresets = () => {
    setLoading(true)
    fetchApi<Preset[]>('/api/presets/')
      .then(data => {
        const list = Array.isArray(data) ? data : []
        setPresets(list)
        if (list.length > 0 && !selectedId) setSelectedId(list[0].id)
      })
      .catch(() => setPresets([]))
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadPresets() }, [])

  const selected = presets.find(p => p.id === selectedId)

  const saveSteps = async (steps: PresetStep[]) => {
    if (!selected) return
    setSaving(true)
    try {
      await fetchApi(`/api/presets/${selected.id}`, {
        method: 'PUT',
        body: JSON.stringify({ name: selected.name, description: selected.description, steps }),
      })
      loadPresets()
    } catch { /* error */ }
    finally { setSaving(false) }
  }

  const handleStepSave = () => {
    if (!selected || editStepIdx === null) return
    const newSteps = [...(selected.steps || [])]
    newSteps[editStepIdx] = { ...editStepData, step_number: editStepIdx + 1 }
    saveSteps(newSteps)
    setEditStepIdx(null)
  }

  const addStep = () => {
    if (!selected) return
    const steps = [...(selected.steps || []), { ...defaultStep, step_number: (selected.steps?.length || 0) + 1 }]
    saveSteps(steps)
  }

  const removeStep = (idx: number) => {
    if (!selected) return
    const steps = (selected.steps || []).filter((_, i) => i !== idx).map((s, i) => ({ ...s, step_number: i + 1 }))
    saveSteps(steps)
  }

  const handleCreate = async () => {
    if (!newCode.trim() || !newName.trim()) return
    setSaving(true)
    try {
      await fetchApi('/api/presets/', {
        method: 'POST',
        body: JSON.stringify({ code: newCode.trim(), name: newName.trim(), description: newDesc.trim(), steps: [defaultStep] }),
      })
      setCreateOpen(false)
      setNewCode('')
      setNewName('')
      setNewDesc('')
      loadPresets()
    } catch { /* error */ }
    finally { setSaving(false) }
  }

  const handleDelete = async (preset: Preset) => {
    if (!confirm(`프리셋 "${preset.name}"을(를) 삭제할까요?`)) return
    try {
      await fetchApi(`/api/presets/${preset.id}`, { method: 'DELETE' })
      if (selectedId === preset.id) setSelectedId(null)
      loadPresets()
    } catch { /* error */ }
  }

  return (
    <ContentSection title='프리셋' desc='캠페인에 사용할 댓글 대화 시나리오를 관리합니다.'>
      <div>
      <div className='flex gap-4 h-[600px] -mx-1'>
        {/* Left: Preset List */}
        <div className='w-[220px] flex-shrink-0 border border-border rounded-xl overflow-hidden flex flex-col'>
          <div className='p-3 border-b border-border flex items-center justify-between'>
            <span className='text-foreground font-semibold text-[14px]'>프리셋</span>
            <Button variant='ghost' size='icon' className='h-7 w-7' onClick={() => setCreateOpen(true)}>
              <Plus className='h-4 w-4' />
            </Button>
          </div>
          <div className='flex-1 overflow-y-auto'>
            {loading ? (
              <div className='p-3 space-y-2'>
                {[1, 2, 3].map(i => <div key={i} className='hydra-skeleton h-12 rounded-lg' />)}
              </div>
            ) : presets.length === 0 ? (
              <div className='p-4 text-center'>
                <p className='text-muted-foreground text-[12px]'>프리셋이 없어요</p>
              </div>
            ) : (
              presets.map(p => (
                <div
                  key={p.id}
                  className={`px-3 py-2.5 cursor-pointer border-b border-border/30 transition-colors ${
                    selectedId === p.id ? 'bg-primary/10 border-l-2 border-l-primary' : 'hover:bg-muted/50'
                  }`}
                  onClick={() => setSelectedId(p.id)}
                >
                  <div className='flex items-center justify-between'>
                    <span className='font-mono text-[11px] text-muted-foreground'>{p.code}</span>
                    <span className='text-muted-foreground text-[11px]'>{p.steps?.length || 0}스텝</span>
                  </div>
                  <span className='text-foreground text-[13px] font-medium'>{p.name}</span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right: Conversation Preview */}
        <div className='flex-1 border border-border rounded-xl overflow-hidden flex flex-col'>
          {selected ? (
            <>
              <div className='p-4 border-b border-border flex items-center justify-between'>
                <div>
                  <span className='text-foreground font-semibold text-[15px]'>{selected.name}</span>
                  <span className='ml-2 font-mono text-[11px] text-muted-foreground'>{selected.code}</span>
                </div>
                <div className='flex gap-1'>
                  {!selected.is_system && (
                    <Button variant='ghost' size='icon' className='h-7 w-7 text-destructive' onClick={() => handleDelete(selected)}>
                      <Trash2 className='h-3.5 w-3.5' />
                    </Button>
                  )}
                </div>
              </div>
              <div className='flex-1 overflow-y-auto p-4 space-y-1'>
                {(selected.steps || []).map((step, idx) => (
                  <div key={idx}>
                    {/* Delay indicator between steps */}
                    {idx > 0 && (
                      <div className='flex items-center justify-center py-2 text-muted-foreground text-[11px]'>
                        <span>↓ {selected.steps[idx - 1]?.delay_min || 5}~{selected.steps[idx - 1]?.delay_max || 25}분 후</span>
                      </div>
                    )}
                    {/* Step card */}
                    <div
                      className={`rounded-lg border border-border/50 p-3 cursor-pointer hover:border-primary/50 transition-colors ${
                        step.type === 'reply' ? 'ml-8' : ''
                      }`}
                      onClick={() => { setEditStepIdx(idx); setEditStepData({ ...step }) }}
                    >
                      <div className='flex items-center gap-2 mb-1'>
                        <div
                          className='w-6 h-6 rounded-full flex items-center justify-center text-white text-[10px] font-bold'
                          style={{ background: roleColors[step.role] || '#71717a' }}
                        >
                          {idx + 1}
                        </div>
                        <span className='hydra-tag' style={{
                          background: `${roleColors[step.role] || '#71717a'}20`,
                          color: roleColors[step.role] || '#71717a',
                        }}>
                          {roleLabels[step.role] || step.role}
                        </span>
                        <span className='text-muted-foreground text-[11px]'>
                          {typeLabels[step.type] || step.type}
                        </span>
                        {step.target && step.target !== 'video' && (
                          <span className='text-muted-foreground text-[11px]'>→ {step.target}</span>
                        )}
                      </div>
                      <div className='flex items-center justify-between'>
                        <span className='text-muted-foreground text-[12px]'>
                          {step.tone || '톤 미설정'}
                        </span>
                        {step.like_count > 0 && (
                          <span className='text-muted-foreground text-[11px]'>좋아요 {step.like_count}개</span>
                        )}
                      </div>
                    </div>
                  </div>
                ))}

                {/* Add step button */}
                <div className='pt-3'>
                  <Button variant='outline' size='sm' onClick={addStep} className='hydra-btn-press w-full' disabled={saving}>
                    <Plus className='mr-1 h-3 w-3' /> 스텝 추가
                  </Button>
                </div>
              </div>
            </>
          ) : (
            <div className='flex-1 flex items-center justify-center text-muted-foreground text-[13px]'>
              {loading ? '로딩 중...' : '좌측에서 프리셋을 선택하세요'}
            </div>
          )}
        </div>
      </div>

      {/* Step Edit Modal */}
      <Dialog open={editStepIdx !== null} onOpenChange={(v) => { if (!v) setEditStepIdx(null) }}>
        <DialogContent className='sm:max-w-sm'>
          <DialogHeader>
            <DialogTitle>스텝 {editStepIdx !== null ? editStepIdx + 1 : ''} 편집</DialogTitle>
          </DialogHeader>
          <div className='space-y-4 py-2'>
            <div className='mb-5'>
              <label className='text-foreground text-sm font-medium mb-1.5'>역할</label>
              <Select value={editStepData.role} onValueChange={v => setEditStepData(prev => ({ ...prev, role: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {roles.map(r => <SelectItem key={r} value={r}>{roleLabels[r] || r}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className='mb-5'>
              <label className='text-foreground text-sm font-medium mb-1.5'>유형</label>
              <Select value={editStepData.type} onValueChange={v => setEditStepData(prev => ({ ...prev, type: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {types.map(t => <SelectItem key={t} value={t}>{typeLabels[t]}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className='mb-5'>
              <label className='text-foreground text-sm font-medium mb-1.5'>톤/분위기</label>
              <p className='text-muted-foreground text-xs mb-2'>어떤 톤으로 작성할까요?</p>
              <Input value={editStepData.tone} onChange={e => setEditStepData(prev => ({ ...prev, tone: e.target.value }))} placeholder='예: 공감, 궁금함, 추천' />
            </div>
            <div className='mb-5'>
              <label className='text-foreground text-sm font-medium mb-1.5'>대상</label>
              <Input value={editStepData.target} onChange={e => setEditStepData(prev => ({ ...prev, target: e.target.value }))} placeholder='예: video, main, step1' />
            </div>
            <div className='grid grid-cols-2 gap-3'>
              <div className='mb-5'>
                <label className='text-foreground text-sm font-medium mb-1.5'>좋아요 수</label>
                <Input type='number' min={0} value={editStepData.like_count} onChange={e => setEditStepData(prev => ({ ...prev, like_count: parseInt(e.target.value) || 0 }))} />
              </div>
              <div />
            </div>
            <div className='grid grid-cols-2 gap-3'>
              <div className='mb-5'>
                <label className='text-foreground text-sm font-medium mb-1.5'>최소 딜레이 (분)</label>
                <Input type='number' min={0} value={editStepData.delay_min} onChange={e => setEditStepData(prev => ({ ...prev, delay_min: parseInt(e.target.value) || 0 }))} />
              </div>
              <div className='mb-5'>
                <label className='text-foreground text-sm font-medium mb-1.5'>최대 딜레이 (분)</label>
                <Input type='number' min={0} value={editStepData.delay_max} onChange={e => setEditStepData(prev => ({ ...prev, delay_max: parseInt(e.target.value) || 0 }))} />
              </div>
            </div>
          </div>
          <DialogFooter className='flex !justify-between'>
            <Button
              variant='ghost'
              className='text-destructive hover:text-destructive hover:bg-destructive/10 hydra-btn-press'
              onClick={() => { if (editStepIdx !== null) { removeStep(editStepIdx); setEditStepIdx(null) } }}
            >
              삭제
            </Button>
            <div className='flex gap-2'>
              <Button variant='outline' onClick={() => setEditStepIdx(null)} className='hydra-btn-press'>취소</Button>
              <Button onClick={handleStepSave} disabled={saving} className='hydra-btn-press'>
                {saving ? '저장 중...' : '저장'}
              </Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Create Preset Modal */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className='sm:max-w-sm'>
          <DialogHeader>
            <DialogTitle>새 프리셋 만들기</DialogTitle>
          </DialogHeader>
          <div className='space-y-4 py-2'>
            <div className='mb-5'>
              <label className='text-foreground text-sm font-medium mb-1.5'>프리셋 코드</label>
              <p className='text-muted-foreground text-xs mb-2'>영문 소문자와 언더스코어만 사용 (예: gentle_boost)</p>
              <Input value={newCode} onChange={e => setNewCode(e.target.value)} placeholder='gentle_boost' />
            </div>
            <div className='mb-5'>
              <label className='text-foreground text-sm font-medium mb-1.5'>프리셋 이름</label>
              <Input value={newName} onChange={e => setNewName(e.target.value)} placeholder='부드러운 부스팅' />
            </div>
            <div className='mb-5'>
              <label className='text-foreground text-sm font-medium mb-1.5'>설명</label>
              <Input value={newDesc} onChange={e => setNewDesc(e.target.value)} placeholder='프리셋에 대한 간단한 설명' />
            </div>
          </div>
          <DialogFooter>
            <Button variant='outline' onClick={() => setCreateOpen(false)} className='hydra-btn-press'>취소</Button>
            <Button onClick={handleCreate} disabled={saving || !newCode.trim() || !newName.trim()} className='hydra-btn-press'>
              {saving ? '생성 중...' : '생성'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      </div>
    </ContentSection>
  )
}
