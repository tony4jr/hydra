import { useEffect, useState } from 'react'
import { Plus, Pencil, Trash2, X } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
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

const defaultSteps: PresetStep[] = [
  {
    step_number: 1,
    role: 'supporter',
    type: 'comment',
    tone: 'positive',
    target: 'video',
    like_count: 0,
    delay_min: 30,
    delay_max: 120,
  },
]

export function SettingsPresets() {
  const [presets, setPresets] = useState<Preset[]>([])
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingPreset, setEditingPreset] = useState<Preset | null>(null)
  const [formName, setFormName] = useState('')
  const [formCode, setFormCode] = useState('')
  const [formDescription, setFormDescription] = useState('')
  const [formSteps, setFormSteps] = useState<PresetStep[]>([])
  const [saving, setSaving] = useState(false)

  const loadPresets = () => {
    fetchApi<Preset[]>('/api/presets/')
      .then((data) => setPresets(Array.isArray(data) ? data : []))
      .catch(() => {})
  }

  useEffect(() => {
    loadPresets()
  }, [])

  const openCreate = () => {
    setEditingPreset(null)
    setFormName('')
    setFormCode('')
    setFormDescription('')
    setFormSteps([...defaultSteps])
    setDialogOpen(true)
  }

  const openEdit = (preset: Preset) => {
    setEditingPreset(preset)
    setFormName(preset.name)
    setFormCode(preset.code)
    setFormDescription(preset.description || '')
    setFormSteps(preset.steps?.length ? [...preset.steps] : [...defaultSteps])
    setDialogOpen(true)
  }

  const updateStep = (index: number, field: keyof PresetStep, value: string | number) => {
    setFormSteps((prev) => {
      const next = [...prev]
      next[index] = { ...next[index], [field]: value }
      return next
    })
  }

  const addStep = () => {
    setFormSteps((prev) => [
      ...prev,
      {
        step_number: prev.length + 1,
        role: 'seed',
        type: 'comment',
        tone: '',
        target: 'main',
        like_count: 0,
        delay_min: 30,
        delay_max: 120,
      },
    ])
  }

  const removeStep = (index: number) => {
    setFormSteps((prev) =>
      prev
        .filter((_, i) => i !== index)
        .map((s, i) => ({ ...s, step_number: i + 1 }))
    )
  }

  const handleSave = async () => {
    const steps = formSteps.map((s, i) => ({ ...s, step_number: i + 1 }))

    setSaving(true)
    try {
      if (editingPreset) {
        await fetchApi(`/api/presets/${editingPreset.id}`, {
          method: 'PUT',
          body: JSON.stringify({
            name: formName,
            description: formDescription,
            steps,
          }),
        })
      } else {
        await fetchApi('/api/presets/', {
          method: 'POST',
          body: JSON.stringify({
            code: formCode,
            name: formName,
            description: formDescription,
            steps,
          }),
        })
      }
      setDialogOpen(false)
      loadPresets()
    } catch {
      alert('저장 실패')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (preset: Preset) => {
    if (!confirm(`프리셋 "${preset.name}"을(를) 삭제하시겠습니까?`)) return
    try {
      await fetchApi(`/api/presets/${preset.id}`, { method: 'DELETE' })
      loadPresets()
    } catch {
      alert('삭제 실패')
    }
  }

  return (
    <ContentSection
      title='프리셋'
      desc='캠페인에 사용할 댓글 프리셋을 관리합니다.'
    >
      <div className='space-y-4'>
        <div className='flex justify-end'>
          <Button size='sm' onClick={openCreate}>
            <Plus className='mr-2 h-4 w-4' />
            새 프리셋
          </Button>
        </div>

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>코드</TableHead>
              <TableHead>이름</TableHead>
              <TableHead className='text-center'>유형</TableHead>
              <TableHead className='text-center'>스텝 수</TableHead>
              <TableHead className='text-right'>작업</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {presets.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={5}
                  className='py-10 text-center text-muted-foreground'
                >
                  등록된 프리셋이 없습니다.
                </TableCell>
              </TableRow>
            ) : (
              presets.map((preset) => (
                <TableRow key={preset.id}>
                  <TableCell className='font-mono text-sm'>
                    {preset.code}
                  </TableCell>
                  <TableCell>{preset.name}</TableCell>
                  <TableCell className='text-center'>
                    {preset.is_system ? (
                      <Badge variant='secondary'>시스템</Badge>
                    ) : (
                      <Badge variant='outline'>커스텀</Badge>
                    )}
                  </TableCell>
                  <TableCell className='text-center'>
                    {preset.steps?.length || 0}
                  </TableCell>
                  <TableCell className='text-right'>
                    <div className='flex justify-end gap-1'>
                      <Button
                        variant='ghost'
                        size='icon'
                        onClick={() => openEdit(preset)}
                      >
                        <Pencil className='h-4 w-4' />
                      </Button>
                      {!preset.is_system && (
                        <Button
                          variant='ghost'
                          size='icon'
                          onClick={() => handleDelete(preset)}
                        >
                          <Trash2 className='h-4 w-4 text-destructive' />
                        </Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>

        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogContent className='max-w-2xl'>
            <DialogHeader>
              <DialogTitle>
                {editingPreset ? '프리셋 수정' : '새 프리셋 만들기'}
              </DialogTitle>
              <DialogDescription>
                프리셋 정보와 스텝을 설정합니다.
              </DialogDescription>
            </DialogHeader>
            <div className='grid gap-4 py-4'>
              <div className='grid grid-cols-2 gap-4'>
                <div className='space-y-2'>
                  <Label htmlFor='preset-code'>코드</Label>
                  <Input
                    id='preset-code'
                    placeholder='예: gentle_boost'
                    value={formCode}
                    onChange={(e) => setFormCode(e.target.value)}
                    disabled={!!editingPreset}
                  />
                </div>
                <div className='space-y-2'>
                  <Label htmlFor='preset-name'>이름</Label>
                  <Input
                    id='preset-name'
                    placeholder='예: 부드러운 부스팅'
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                  />
                </div>
              </div>
              <div className='space-y-2'>
                <Label htmlFor='preset-desc'>설명</Label>
                <Input
                  id='preset-desc'
                  placeholder='프리셋에 대한 간단한 설명'
                  value={formDescription}
                  onChange={(e) => setFormDescription(e.target.value)}
                />
              </div>
              <div className='space-y-2'>
                <Label>스텝 편집기</Label>
                <div className='space-y-3 max-h-[300px] overflow-y-auto'>
                  {formSteps.map((step, i) => (
                    <div
                      key={i}
                      className='grid grid-cols-8 gap-2 items-center border p-2 rounded'
                    >
                      <span className='text-sm text-muted-foreground text-center'>
                        #{i + 1}
                      </span>
                      <Select
                        value={step.role}
                        onValueChange={(v) => updateStep(i, 'role', v)}
                      >
                        <SelectTrigger className='h-8 text-xs'>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value='seed'>시드</SelectItem>
                          <SelectItem value='asker'>질문자</SelectItem>
                          <SelectItem value='witness'>목격자</SelectItem>
                          <SelectItem value='agree'>동조자</SelectItem>
                          <SelectItem value='curious'>궁금이</SelectItem>
                          <SelectItem value='info'>정보통</SelectItem>
                          <SelectItem value='fan'>팬</SelectItem>
                          <SelectItem value='qa'>QA</SelectItem>
                        </SelectContent>
                      </Select>
                      <Select
                        value={step.type}
                        onValueChange={(v) => updateStep(i, 'type', v)}
                      >
                        <SelectTrigger className='h-8 text-xs'>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value='comment'>댓글</SelectItem>
                          <SelectItem value='reply'>대댓글</SelectItem>
                        </SelectContent>
                      </Select>
                      <Input
                        className='h-8 text-xs'
                        placeholder='톤'
                        value={step.tone}
                        onChange={(e) => updateStep(i, 'tone', e.target.value)}
                      />
                      <Input
                        className='h-8 text-xs'
                        placeholder='대상'
                        value={step.target}
                        onChange={(e) =>
                          updateStep(i, 'target', e.target.value)
                        }
                      />
                      <Input
                        className='h-8 text-xs'
                        type='number'
                        placeholder='좋아요'
                        value={step.like_count}
                        onChange={(e) =>
                          updateStep(i, 'like_count', parseInt(e.target.value) || 0)
                        }
                      />
                      <Input
                        className='h-8 text-xs'
                        type='number'
                        placeholder='딜레이(분)'
                        value={step.delay_min}
                        onChange={(e) =>
                          updateStep(i, 'delay_min', parseInt(e.target.value) || 0)
                        }
                      />
                      <Button
                        variant='ghost'
                        size='sm'
                        className='h-8 w-8 p-0'
                        onClick={() => removeStep(i)}
                      >
                        <X className='h-4 w-4' />
                      </Button>
                    </div>
                  ))}
                </div>
                <Button variant='outline' size='sm' onClick={addStep}>
                  <Plus className='mr-1 h-3 w-3' /> 스텝 추가
                </Button>
              </div>
            </div>
            <DialogFooter>
              <Button
                variant='outline'
                onClick={() => setDialogOpen(false)}
              >
                취소
              </Button>
              <Button onClick={handleSave} disabled={saving}>
                {saving ? '저장 중...' : '저장'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </ContentSection>
  )
}
