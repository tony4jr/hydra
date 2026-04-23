import { useEffect, useState } from 'react'
import { Card } from '@/components/ui/card'
import { fetchApi } from '@/lib/api'

type Stats = {
  pending: number
  running: number
  done: number
  failed: number
  by_type: Record<string, { pending: number; running: number; done: number; failed: number }>
}

export function TaskStatsPanel() {
  const [stats, setStats] = useState<Stats | null>(null)

  useEffect(() => {
    const load = () => {
      fetchApi<Stats>('/api/admin/tasks/stats')
        .then(setStats)
        .catch(() => {})
    }
    load()
    const id = setInterval(load, 5_000)
    return () => clearInterval(id)
  }, [])

  if (!stats) return null

  return (
    <div className='space-y-3'>
      <div className='grid grid-cols-4 gap-3'>
        <Card className='p-3'>
          <div className='text-xs text-muted-foreground'>대기</div>
          <div className='text-2xl font-bold'>{stats.pending}</div>
        </Card>
        <Card className='p-3'>
          <div className='text-xs text-muted-foreground'>실행중</div>
          <div className='text-2xl font-bold text-amber-500'>{stats.running}</div>
        </Card>
        <Card className='p-3'>
          <div className='text-xs text-muted-foreground'>완료</div>
          <div className='text-2xl font-bold text-green-500'>{stats.done}</div>
        </Card>
        <Card className='p-3'>
          <div className='text-xs text-muted-foreground'>실패</div>
          <div className='text-2xl font-bold text-destructive'>{stats.failed}</div>
        </Card>
      </div>

      {Object.keys(stats.by_type).length > 0 && (
        <Card className='overflow-hidden'>
          <table className='w-full text-sm'>
            <thead className='bg-muted/40 text-xs uppercase text-muted-foreground'>
              <tr>
                <th className='px-3 py-2 text-left'>Task Type</th>
                <th className='px-3 py-2 text-right'>대기</th>
                <th className='px-3 py-2 text-right'>실행</th>
                <th className='px-3 py-2 text-right'>완료</th>
                <th className='px-3 py-2 text-right'>실패</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(stats.by_type).map(([type, counts]) => (
                <tr key={type} className='border-t'>
                  <td className='px-3 py-2 font-mono'>{type}</td>
                  <td className='px-3 py-2 text-right'>{counts.pending}</td>
                  <td className='px-3 py-2 text-right text-amber-500'>{counts.running}</td>
                  <td className='px-3 py-2 text-right text-green-500'>{counts.done}</td>
                  <td className='px-3 py-2 text-right text-destructive'>{counts.failed}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  )
}
