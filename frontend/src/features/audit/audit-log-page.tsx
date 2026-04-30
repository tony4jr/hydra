import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { http as axios } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

type AuditItem = {
  id: number
  user_id: number | null
  action: string
  target_type: string | null
  target_id: number | null
  metadata: Record<string, unknown> | null
  ip_address: string | null
  user_agent: string | null
  timestamp: string
}

type AuditResponse = {
  items: AuditItem[]
  total: number
  limit: number
  offset: number
}

const ACTIONS = [
  'all',
  'login',
  'logout',
  'deploy',
  'pause',
  'unpause',
  'canary_change',
  'campaign_change',
  'avatar_change',
  'worker_change',
  'account_change',
  'preset_change',
  'brand_change',
]

const PAGE_SIZE = 50

export function AuditLogPage() {
  const [action, setAction] = useState('all')
  const [userIdInput, setUserIdInput] = useState('')
  const [offset, setOffset] = useState(0)

  const params: Record<string, string> = {
    limit: String(PAGE_SIZE),
    offset: String(offset),
  }
  if (action !== 'all') params.action = action
  if (userIdInput.trim()) params.user_id = userIdInput.trim()

  const query = new URLSearchParams(params).toString()

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['audit-log', query],
    queryFn: async () => {
      const r = await axios.get<AuditResponse>(
        `${API_BASE}/api/admin/audit/list?${query}`,
      )
      return r.data
    },
  })

  const page = Math.floor(offset / PAGE_SIZE) + 1
  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  const applyFilters = () => {
    setOffset(0)
    refetch()
  }

  return (
    <>
      <Header fixed>
        <div className='ml-auto flex items-center space-x-4'>
          <ThemeSwitch />
          <ProfileDropdown />
        </div>
      </Header>
      <Main>
        <div className='space-y-5'>
          <div>
            <h1 className='hydra-page-h'>감사 로그</h1>
            <p className='hydra-page-sub'>
              /api/admin/* 쓰기 작업 이력 · {data?.total ?? 0}건
            </p>
          </div>

          <Card className='p-4'>
            <div className='flex flex-wrap items-end gap-3'>
              <div className='min-w-[160px] flex-1'>
                <Label>Action</Label>
                <Select value={action} onValueChange={setAction}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {ACTIONS.map((a) => (
                      <SelectItem key={a} value={a}>
                        {a}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className='min-w-[140px]'>
                <Label>User ID</Label>
                <Input
                  type='number'
                  value={userIdInput}
                  onChange={(e) => setUserIdInput(e.target.value)}
                  placeholder='all'
                />
              </div>
              <Button onClick={applyFilters}>조회</Button>
            </div>
          </Card>

          <Card className='overflow-hidden'>
            <div className='max-h-[60vh] overflow-auto'>
              <table className='w-full text-sm'>
                <thead className='sticky top-0 bg-muted/60 text-left text-xs uppercase text-muted-foreground'>
                  <tr>
                    <th className='px-3 py-2'>시각</th>
                    <th className='px-3 py-2'>Action</th>
                    <th className='px-3 py-2'>User</th>
                    <th className='px-3 py-2'>IP</th>
                    <th className='px-3 py-2'>Metadata</th>
                  </tr>
                </thead>
                <tbody>
                  {isLoading && (
                    <tr>
                      <td colSpan={5} className='p-6 text-center text-muted-foreground'>
                        불러오는 중…
                      </td>
                    </tr>
                  )}
                  {data?.items.length === 0 && !isLoading && (
                    <tr>
                      <td colSpan={5} className='p-6 text-center text-muted-foreground'>
                        기록 없음
                      </td>
                    </tr>
                  )}
                  {data?.items.map((it) => (
                    <tr key={it.id} className='border-t hover:bg-muted/30'>
                      <td className='px-3 py-2 font-mono text-xs'>
                        {new Date(it.timestamp).toLocaleString('ko')}
                      </td>
                      <td className='px-3 py-2 font-medium'>{it.action}</td>
                      <td className='px-3 py-2'>{it.user_id ?? '—'}</td>
                      <td className='px-3 py-2 font-mono text-xs'>
                        {it.ip_address ?? '—'}
                      </td>
                      <td className='px-3 py-2'>
                        <details>
                          <summary className='cursor-pointer text-xs text-muted-foreground'>
                            보기
                          </summary>
                          <pre className='mt-1 max-w-md overflow-x-auto rounded bg-muted/40 p-2 text-[10px]'>
                            {JSON.stringify(it.metadata, null, 2)}
                          </pre>
                        </details>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className='flex items-center justify-between border-t p-3 text-sm'>
              <span className='text-muted-foreground'>
                {page} / {totalPages} 페이지
              </span>
              <div className='flex gap-2'>
                <Button
                  variant='outline'
                  size='sm'
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                >
                  이전
                </Button>
                <Button
                  variant='outline'
                  size='sm'
                  disabled={!data || offset + PAGE_SIZE >= data.total}
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                >
                  다음
                </Button>
              </div>
            </div>
          </Card>
        </div>
      </Main>
    </>
  )
}
