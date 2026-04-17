import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Checkbox } from '@/components/ui/checkbox'
import { fetchApi } from '@/lib/api'

interface Brand {
  id: number
  name: string
}

interface Preset {
  id: number
  name: string
}

interface Video {
  id: number
  title: string
  video_id: string
}

interface CampaignCreateDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSuccess: () => void
}

export function CampaignCreateDialog({
  open,
  onOpenChange,
  onSuccess,
}: CampaignCreateDialogProps) {
  const [brands, setBrands] = useState<Brand[]>([])
  const [presets, setPresets] = useState<Preset[]>([])
  const [videos, setVideos] = useState<Video[]>([])

  const [brandId, setBrandId] = useState('')
  const [presetId, setPresetId] = useState('')
  const [selectedVideoIds, setSelectedVideoIds] = useState<number[]>([])
  const [execMode, setExecMode] = useState('auto')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (open) {
      fetchApi<Brand[]>('/brands/api/list')
        .then(setBrands)
        .catch(() => setBrands([]))
      fetchApi<Preset[]>('/api/presets/')
        .then(setPresets)
        .catch(() => setPresets([]))
      fetchApi<{ items: Video[] }>('/videos/api/list')
        .then((data) => setVideos(data.items || []))
        .catch(() => setVideos([]))
      // reset form
      setBrandId('')
      setPresetId('')
      setSelectedVideoIds([])
      setExecMode('auto')
    }
  }, [open])

  const toggleVideo = (id: number) => {
    setSelectedVideoIds((prev) =>
      prev.includes(id) ? prev.filter((v) => v !== id) : [...prev, id]
    )
  }

  const handleSubmit = async () => {
    if (!brandId) return
    setLoading(true)
    try {
      await fetchApi('/campaigns/api/create', {
        method: 'POST',
        body: JSON.stringify({
          brand_id: parseInt(brandId),
          preset_id: presetId ? parseInt(presetId) : null,
          video_ids: selectedVideoIds,
          exec_mode: execMode,
        }),
      })
      onOpenChange(false)
      onSuccess()
    } catch {
      // error handled silently
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>캠페인 생성</DialogTitle>
        </DialogHeader>
        <div className='grid gap-4 py-2'>
          <div className='grid gap-2'>
            <Label>브랜드 선택 *</Label>
            <Select value={brandId} onValueChange={setBrandId}>
              <SelectTrigger className='w-full'>
                <SelectValue placeholder='브랜드를 선택하세요' />
              </SelectTrigger>
              <SelectContent>
                {brands.map((b) => (
                  <SelectItem key={b.id} value={String(b.id)}>
                    {b.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className='grid gap-2'>
            <Label>프리셋 선택</Label>
            <Select value={presetId} onValueChange={setPresetId}>
              <SelectTrigger className='w-full'>
                <SelectValue placeholder='프리셋을 선택하세요' />
              </SelectTrigger>
              <SelectContent>
                {presets.map((p) => (
                  <SelectItem key={p.id} value={String(p.id)}>
                    {p.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className='grid gap-2'>
            <Label>영상 선택</Label>
            <div className='max-h-40 overflow-y-auto rounded-md border p-2'>
              {videos.length === 0 ? (
                <p className='py-2 text-center text-sm text-muted-foreground'>
                  영상이 없습니다
                </p>
              ) : (
                videos.map((v) => (
                  <label
                    key={v.id}
                    className='flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-muted'
                  >
                    <Checkbox
                      checked={selectedVideoIds.includes(v.id)}
                      onCheckedChange={() => toggleVideo(v.id)}
                    />
                    <span className='truncate'>{v.title || v.video_id}</span>
                  </label>
                ))
              )}
            </div>
            {selectedVideoIds.length > 0 && (
              <p className='text-xs text-muted-foreground'>
                {selectedVideoIds.length}개 선택됨
              </p>
            )}
          </div>

          <div className='grid gap-2'>
            <Label>실행 모드</Label>
            <RadioGroup value={execMode} onValueChange={setExecMode}>
              <div className='flex items-center gap-2'>
                <RadioGroupItem value='auto' id='mode-auto' />
                <Label htmlFor='mode-auto' className='font-normal'>
                  자동 분산
                </Label>
              </div>
              <div className='flex items-center gap-2'>
                <RadioGroupItem value='urgent' id='mode-urgent' />
                <Label htmlFor='mode-urgent' className='font-normal'>
                  긴급
                </Label>
              </div>
            </RadioGroup>
          </div>
        </div>
        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            취소
          </Button>
          <Button onClick={handleSubmit} disabled={loading || !brandId}>
            {loading ? '생성 중...' : '캠페인 생성'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
