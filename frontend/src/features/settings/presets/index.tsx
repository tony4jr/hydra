import { useEffect, useState } from 'react'
import { Plus, Pencil, Trash2 } from 'lucide-react'
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
import { Textarea } from '@/components/ui/textarea'
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
  const [formSteps, setFormSteps] = useState('')
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
    setFormSteps(JSON.stringify(defaultSteps, null, 2))
    setDialogOpen(true)
  }

  const openEdit = (preset: Preset) => {
    setEditingPreset(preset)
    setFormName(preset.name)
    setFormCode(preset.code)
    setFormDescription(preset.description || '')
    setFormSteps(JSON.stringify(preset.steps || [], null, 2))
    setDialogOpen(true)
  }

  const handleSave = async () => {
    let steps: PresetStep[]
    try {
      steps = JSON.parse(formSteps)
    } catch {
      alert('Steps JSON이 올바르지 않습니다.')
      return
    }

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
                <Label htmlFor='preset-steps'>
                  스텝 (JSON)
                </Label>
                <Textarea
                  id='preset-steps'
                  className='min-h-[200px] font-mono text-sm'
                  value={formSteps}
                  onChange={(e) => setFormSteps(e.target.value)}
                />
                <p className='text-xs text-muted-foreground'>
                  각 스텝: step_number, role, type, tone, target, like_count,
                  delay_min, delay_max
                </p>
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
