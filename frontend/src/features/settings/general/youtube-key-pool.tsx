import { useEffect, useState } from 'react'
import { Plus, Trash2, KeyRound } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { fetchApi } from '@/lib/api'
import { toast } from 'sonner'

interface ApiKeyRow {
  id: number
  key_masked: string
  label: string | null
  status: 'active' | 'exhausted' | 'disabled'
  quota_used: number
  quota_limit: number
  quota_pct: number
  last_used_at: string | null
  exhausted_at: string | null
  created_at: string | null
}

function StatusBadge({ status, pct }: { status: string; pct: number }) {
  if (status === 'exhausted') {
    return <span className='text-destructive text-xs font-medium'>🚫 소진</span>
  }
  if (status === 'disabled') {
    return <span className='text-muted-foreground text-xs font-medium'>⏸ 비활성</span>
  }
  if (pct >= 80) {
    return <span className='text-amber-500 text-xs font-medium'>⚠️ {pct}%</span>
  }
  return <span className='text-emerald-500 text-xs font-medium'>✅ 활성</span>
}

function QuotaBar({ pct, status }: { pct: number; status: string }) {
  const color =
    status === 'exhausted' ? 'bg-destructive'
    : status === 'disabled' ? 'bg-muted-foreground'
    : pct >= 80 ? 'bg-amber-500'
    : 'bg-emerald-500'
  return (
    <div className='w-32 h-1.5 bg-muted rounded-full overflow-hidden'>
      <div
        className={`h-full ${color} transition-all duration-500`}
        style={{ width: `${Math.min(100, pct)}%` }}
      />
    </div>
  )
}

export function YouTubeKeyPool() {
  const [keys, setKeys] = useState<ApiKeyRow[]>([])
  const [loading, setLoading] = useState(true)
  const [adding, setAdding] = useState(false)
  const [newKey, setNewKey] = useState('')
  const [newLabel, setNewLabel] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const data = await fetchApi<{ keys: ApiKeyRow[] }>('/api/admin/youtube-keys')
      setKeys(data.keys || [])
    } catch (e) {
      toast.error('키 목록 불러오기 실패', {
        description: e instanceof Error ? e.message : String(e),
      })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const handleAdd = async () => {
    if (!newKey.trim()) return
    setSubmitting(true)
    try {
      await fetchApi('/api/admin/youtube-keys', {
        method: 'POST',
        body: JSON.stringify({ key: newKey.trim(), label: newLabel.trim() || null }),
      })
      toast.success('키 추가됨')
      setNewKey('')
      setNewLabel('')
      setAdding(false)
      await load()
    } catch (e) {
      toast.error('추가 실패', {
        description: e instanceof Error ? e.message : String(e),
      })
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('이 키를 삭제하시겠습니까?')) return
    try {
      await fetchApi(`/api/admin/youtube-keys/${id}`, { method: 'DELETE' })
      toast.success('삭제됨')
      await load()
    } catch (e) {
      toast.error('삭제 실패', {
        description: e instanceof Error ? e.message : String(e),
      })
    }
  }

  return (
    <div>
      <div className='flex items-center gap-2 mb-3'>
        <KeyRound className='h-4 w-4 text-muted-foreground' />
        <h4 className='text-foreground font-semibold text-[14px]'>
          YouTube Data API v3 키 풀
        </h4>
        <span className='text-muted-foreground text-xs'>
          ({keys.length}개 등록, 라운드로빈)
        </span>
      </div>
      <p className='text-muted-foreground text-xs mb-3'>
        키를 여러 개 등록하면 자동으로 분산 호출됩니다. 일일 한도 소진 시 자동으로 다음 키로 회전.
      </p>

      <div className='space-y-2'>
        {loading ? (
          <div className='text-muted-foreground text-sm py-4'>불러오는 중...</div>
        ) : keys.length === 0 ? (
          <div className='text-muted-foreground text-sm py-4 text-center border border-dashed rounded-md'>
            등록된 키가 없습니다. 아래 버튼으로 추가하세요.
          </div>
        ) : (
          keys.map((k) => (
            <div
              key={k.id}
              className='flex items-center gap-3 px-3 py-2 rounded-md border bg-card/50 hover:bg-card transition-colors'
            >
              <code className='text-foreground/90 font-mono text-sm flex-1 truncate'>
                {k.key_masked}
                {k.label && (
                  <span className='ml-2 text-muted-foreground text-xs'>· {k.label}</span>
                )}
              </code>
              <StatusBadge status={k.status} pct={k.quota_pct} />
              <QuotaBar pct={k.quota_pct} status={k.status} />
              <Button
                variant='ghost'
                size='sm'
                onClick={() => handleDelete(k.id)}
                className='text-muted-foreground hover:text-destructive'
              >
                <Trash2 className='h-3.5 w-3.5 mr-1' />
                삭제
              </Button>
            </div>
          ))
        )}
      </div>

      {adding ? (
        <div className='mt-3 p-3 border rounded-md space-y-2 bg-card/30'>
          <Input
            placeholder='AIzaSy... (YouTube Data API v3 키)'
            value={newKey}
            onChange={(e) => setNewKey(e.target.value)}
            className='font-mono text-sm'
          />
          <Input
            placeholder='라벨 (선택, 예: 메인 계정)'
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)}
          />
          <div className='flex gap-2 justify-end'>
            <Button
              variant='ghost'
              size='sm'
              onClick={() => {
                setAdding(false)
                setNewKey('')
                setNewLabel('')
              }}
            >
              취소
            </Button>
            <Button size='sm' onClick={handleAdd} disabled={submitting || !newKey.trim()}>
              {submitting ? '추가 중...' : '추가'}
            </Button>
          </div>
        </div>
      ) : (
        <Button
          variant='outline'
          size='sm'
          onClick={() => setAdding(true)}
          className='mt-3 hydra-btn-press'
        >
          <Plus className='h-3.5 w-3.5 mr-1.5' />
          새 API 키 추가
        </Button>
      )}
    </div>
  )
}
