import { useEffect, useState } from 'react'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { fetchApi } from '@/lib/api'

interface IpHistoryEntry {
  account_id: number
  account_gmail: string
  ip_address: string
  device_id: string | null
  started_at: string
  ended_at: string | null
  duration_sec: number | null
}

interface IpConflict {
  ip_address: string
  accounts: Array<{ account_id: number; gmail: string; started_at: string }>
  conflict_at: string
}

function shortIp(ip: string): string {
  // IPv6 약어 / IPv4 그대로
  if (ip.includes(':')) {
    const parts = ip.split(':')
    return parts.length > 4 ? `${parts.slice(0, 2).join(':')}::${parts.slice(-1)}` : ip
  }
  return ip
}

export default function IpMonitorPage() {
  const [history, setHistory] = useState<IpHistoryEntry[]>([])
  const [conflicts, setConflicts] = useState<IpConflict[]>([])
  const [loading, setLoading] = useState(true)
  const [hours, setHours] = useState(24)

  const load = async () => {
    try {
      const [h, c] = await Promise.all([
        fetchApi<IpHistoryEntry[]>(`/api/admin/workers/ip-history?hours=${hours}&limit=500`),
        fetchApi<IpConflict[]>(`/api/admin/workers/ip-conflicts?hours=${hours}`),
      ])
      setHistory(h); setConflicts(c)
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => { load() }, [hours])
  useEffect(() => { const t = setInterval(load, 30_000); return () => clearInterval(t) }, [hours])

  return (
    <>
      <Header>
        <div className='ms-auto flex items-center space-x-4'>
          <ThemeSwitch />
          <ProfileDropdown />
        </div>
      </Header>
      <Main>
        <div className='mb-4'>
          <h1 className='text-2xl font-bold'>Exit IP 감시</h1>
          <p className='text-muted-foreground text-sm'>
            워커들이 사용한 외부 IP 이력. 같은 IP × 다계정 = 안티디텍션 위험.
          </p>
        </div>

        <div className='mb-4 flex gap-2'>
          {[6, 24, 72, 168].map((h) => (
            <button
              key={h}
              onClick={() => setHours(h)}
              className={`rounded border px-3 py-1 text-sm ${hours === h ? 'border-primary bg-primary text-primary-foreground' : 'border-border'}`}
            >
              {h}h
            </button>
          ))}
        </div>

        {conflicts.length > 0 && (
          <div className='mb-6'>
            <h2 className='text-destructive mb-2 text-lg font-semibold'>
              ⚠️ 충돌 {conflicts.length}건 (동일 IP × 다계정)
            </h2>
            <div className='border-destructive/40 bg-destructive/5 rounded border'>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>IP</TableHead>
                    <TableHead>계정</TableHead>
                    <TableHead>최초 충돌</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {conflicts.map((c) => (
                    <TableRow key={c.ip_address}>
                      <TableCell className='font-mono text-xs'>{shortIp(c.ip_address)}</TableCell>
                      <TableCell>
                        {c.accounts.map((a) => (
                          <Badge key={a.account_id} variant='outline' className='mr-1 mb-1 text-xs'>
                            {a.gmail}
                          </Badge>
                        ))}
                      </TableCell>
                      <TableCell className='text-xs'>{new Date(c.conflict_at).toLocaleString('ko')}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        )}

        <h2 className='mb-2 text-lg font-semibold'>이력 ({history.length}건)</h2>
        <div className='bg-card rounded-xl border'>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className='w-[140px]'>시각</TableHead>
                <TableHead className='w-[160px]'>계정</TableHead>
                <TableHead>IP</TableHead>
                <TableHead className='w-[80px]'>지속</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading && (
                <TableRow><TableCell colSpan={4}><Skeleton className='h-8 w-full' /></TableCell></TableRow>
              )}
              {!loading && history.length === 0 && (
                <TableRow>
                  <TableCell colSpan={4} className='text-muted-foreground py-8 text-center'>
                    이력 없음
                  </TableCell>
                </TableRow>
              )}
              {history.map((h, i) => (
                <TableRow key={i}>
                  <TableCell className='text-xs'>
                    {new Date(h.started_at).toLocaleString('ko')}
                  </TableCell>
                  <TableCell className='font-mono text-xs'>{h.account_gmail}</TableCell>
                  <TableCell className='font-mono text-xs'>
                    {h.ip_address}
                    {conflicts.some((c) => c.ip_address === h.ip_address) && (
                      <Badge variant='destructive' className='ml-2 text-[10px]'>충돌</Badge>
                    )}
                  </TableCell>
                  <TableCell className='text-xs'>
                    {h.duration_sec !== null ? `${h.duration_sec}s` : '진행중'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Main>
    </>
  )
}
