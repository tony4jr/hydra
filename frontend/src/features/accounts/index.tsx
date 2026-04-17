import { useEffect, useState } from 'react'
import {
  Users, CheckCircle2, Flame, Snowflake, ShieldOff, Ghost,
  ChevronLeft, ChevronRight,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { fetchApi } from '@/lib/api'
import { useCountUp } from '@/hooks/use-count-up'
import { AccountDetailSheet } from './account-detail-sheet'

interface Account {
  id: number
  gmail: string
  status: string
  persona_name?: string | null
  adspower_profile_id: string | null
  success_rate: number
  ghost_count: number
  today_tasks?: number
  last_active_at: string | null
}

interface AccountStats {
  total: number
  active: number
  warmup: number
  cooldown: number
  retired: number
  ghost: number
}

const statusDot: Record<string, string> = {
  active: 'bg-green-500', warmup: 'bg-yellow-500', cooldown: 'bg-blue-500',
  retired: 'bg-red-500', ghost: 'bg-orange-500', registered: 'bg-gray-400',
  profile_set: 'bg-gray-400',
}
const statusLabels: Record<string, string> = {
  active: '활성', warmup: '워밍업', cooldown: '쿨다운',
  retired: '정지', ghost: '고스트', registered: '등록됨', profile_set: '프로필 설정',
}
const statusTagClass: Record<string, string> = {
  active: 'hydra-tag-success', warmup: 'hydra-tag-warning', cooldown: 'hydra-tag-blue',
  retired: 'hydra-tag-danger', ghost: 'hydra-tag-ghost', registered: 'hydra-tag-muted',
  profile_set: 'hydra-tag-muted',
}

function StatCardClickable({ label, value, icon: Icon, color, active, onClick }: {
  label: string; value: number; icon: React.ElementType; color: string; active?: boolean; onClick: () => void
}) {
  const animated = useCountUp(value)
  return (
    <div
      className={`bg-card rounded-xl border border-border p-4 cursor-pointer hydra-btn-press ${active ? 'border-primary' : ''}`}
      onClick={onClick}
    >
      <div className='flex items-center justify-between mb-1'>
        <span className='text-muted-foreground text-[12px]'>{label}</span>
        <Icon className={`h-4 w-4 ${color}`} />
      </div>
      <div className='text-[24px] font-bold'>{animated}</div>
    </div>
  )
}

export default function AccountsPage() {
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null)
  const [sheetOpen, setSheetOpen] = useState(false)
  const [accounts, setAccounts] = useState<Account[]>([])
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const perPage = 20

  // Warmup state
  const [warmupSelected, setWarmupSelected] = useState<number[]>([])
  const [warmupDay, setWarmupDay] = useState('1')
  const [warmupLoading, setWarmupLoading] = useState(false)
  const [warmupMsg, setWarmupMsg] = useState('')

  const [stats, setStats] = useState<AccountStats>({ total: 0, active: 0, warmup: 0, cooldown: 0, retired: 0, ghost: 0 })

  useEffect(() => {
    setLoading(true)
    Promise.all([
      fetchApi<Record<string, number>>('/accounts/api/stats').catch(() => ({} as Record<string, number>)),
      fetchApi<{ items: Account[] }>('/accounts/api/list').catch(() => ({ items: [] })),
    ]).then(([rawStats, a]) => {
      // API는 {registered: 20, active: 5, ...} 형태 — total은 합산
      const total = Object.values(rawStats).reduce((sum, n) => sum + (n || 0), 0)
      setStats({
        total,
        active: rawStats['active'] || 0,
        warmup: rawStats['warmup'] || 0,
        cooldown: rawStats['cooldown'] || 0,
        retired: rawStats['retired'] || 0,
        ghost: (rawStats['ghost'] || 0) + (rawStats['suspended'] || 0),
      })
      setAccounts(a.items || [])
    }).finally(() => setLoading(false))
  }, [])

  const warmupDayDescs: Record<string, string> = {
    '1': 'Day 1: 시청 + 좋아요 + 채널 설정',
    '2': 'Day 2: Gmail/검색 + 댓글 + 구독',
    '3': 'Day 3: 댓글 + 고스트 체크',
  }

  const warmupCandidates = accounts.filter(a =>
    a.status === 'registered' || a.status === 'profile_set' || a.status === 'warmup'
  )

  const filteredAccounts = statusFilter
    ? accounts.filter(a => a.status === statusFilter)
    : accounts

  const totalPages = Math.ceil(filteredAccounts.length / perPage)
  const pagedAccounts = filteredAccounts.slice((page - 1) * perPage, page * perPage)

  const problemAccounts = accounts.filter(a => a.status === 'retired' || a.status === 'ghost')

  const statCards = [
    { label: '전체', value: stats.total, icon: Users, color: 'text-muted-foreground', key: null as string | null },
    { label: '활성', value: stats.active, icon: CheckCircle2, color: 'text-green-500', key: 'active' },
    { label: '워밍업', value: stats.warmup, icon: Flame, color: 'text-yellow-500', key: 'warmup' },
    { label: '쿨다운', value: stats.cooldown, icon: Snowflake, color: 'text-blue-500', key: 'cooldown' },
    { label: '정지', value: stats.retired, icon: ShieldOff, color: 'text-red-500', key: 'retired' },
    { label: '고스트', value: stats.ghost, icon: Ghost, color: 'text-orange-500', key: 'ghost' },
  ]

  const renderTable = (items: Account[]) => (
    <div className='bg-card border border-border rounded-xl overflow-hidden'>
      <div className='overflow-x-auto'>
        <table className='w-full text-sm'>
          <thead>
            <tr className='border-b border-border bg-muted/30'>
              <th className='p-3 text-left font-medium text-[12px] text-muted-foreground'>계정명</th>
              <th className='p-3 text-left font-medium text-[12px] text-muted-foreground'>페르소나</th>
              <th className='p-3 text-center font-medium text-[12px] text-muted-foreground'>상태</th>
              <th className='p-3 text-center font-medium text-[12px] text-muted-foreground'>오늘 작업</th>
              <th className='p-3 text-center font-medium text-[12px] text-muted-foreground'>성공률</th>
              <th className='p-3 text-right font-medium text-[12px] text-muted-foreground'>마지막 활동</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td colSpan={6} className='py-12 text-center text-muted-foreground text-[13px]'>
                  해당하는 계정이 없어요
                </td>
              </tr>
            ) : items.map(acc => (
              <tr
                key={acc.id}
                className='border-b border-border/30 cursor-pointer hydra-row-hover'
                onClick={() => { setSelectedAccountId(acc.id); setSheetOpen(true) }}
              >
                <td className='p-3'>
                  <div className='flex items-center gap-2'>
                    <span className={`inline-block h-2 w-2 rounded-full ${statusDot[acc.status] || 'bg-gray-500'}`} />
                    <span className='text-foreground text-[13px]'>{acc.gmail}</span>
                  </div>
                </td>
                <td className='p-3 text-muted-foreground text-[13px]'>{acc.persona_name || '-'}</td>
                <td className='p-3 text-center'>
                  <span className={`hydra-tag ${statusTagClass[acc.status] || 'hydra-tag-muted'}`}>
                    {statusLabels[acc.status] || acc.status}
                  </span>
                </td>
                <td className='p-3 text-center text-[13px]'>{acc.today_tasks ?? acc.ghost_count ?? 0}</td>
                <td className='p-3 text-center text-[13px]'>{acc.success_rate}%</td>
                <td className='p-3 text-right text-muted-foreground text-[12px]'>
                  {acc.last_active_at ? new Date(acc.last_active_at).toLocaleString('ko') : '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )

  return (
    <>
      <Header fixed>
        <div className='ml-auto flex items-center space-x-4'>
          <ThemeSwitch />
          <ProfileDropdown />
        </div>
      </Header>
      <Main>
        <div >
          <div className='mb-5'>
            <h2 className='text-[22px] font-bold'>계정</h2>
            <p className='text-muted-foreground text-[13px]'>
              YouTube 계정 라이프사이클 관리
            </p>
          </div>

          {/* Stat cards */}
          {loading ? (
            <div className='grid gap-3 grid-cols-3 lg:grid-cols-6 mb-5'>
              {[1, 2, 3, 4, 5, 6].map(i => <Skeleton key={i} className='h-20 rounded-xl' />)}
            </div>
          ) : (
            <div className='grid gap-3 grid-cols-3 lg:grid-cols-6 mb-5'>
              {statCards.map(card => (
                <StatCardClickable
                  key={card.label}
                  label={card.label}
                  value={card.value}
                  icon={card.icon}
                  color={card.color}
                  active={statusFilter === card.key}
                  onClick={() => { setStatusFilter(card.key); setPage(1) }}
                />
              ))}
            </div>
          )}

          <Tabs defaultValue='all'>
            <TabsList>
              <TabsTrigger value='all'>전체 계정</TabsTrigger>
              <TabsTrigger value='warmup'>워밍업</TabsTrigger>
              <TabsTrigger value='problem'>문제 계정</TabsTrigger>
            </TabsList>

            <TabsContent value='all' className='mt-4'>
              {loading ? (
                <Skeleton className='h-64 rounded-xl' />
              ) : (
                <>
                  {renderTable(pagedAccounts)}
                  {totalPages > 1 && (
                    <div className='flex items-center justify-center gap-2 mt-4'>
                      <Button variant='outline' size='icon' className='h-8 w-8' disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
                        <ChevronLeft className='h-4 w-4' />
                      </Button>
                      <span className='text-muted-foreground text-[13px]'>{page} / {totalPages}</span>
                      <Button variant='outline' size='icon' className='h-8 w-8' disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>
                        <ChevronRight className='h-4 w-4' />
                      </Button>
                    </div>
                  )}
                </>
              )}
            </TabsContent>

            <TabsContent value='warmup' className='mt-4'>
              <div className='bg-card border border-border rounded-xl p-5'>
                <div className='mb-4'>
                  <h3 className='text-foreground font-semibold text-[15px] mb-2'>워밍업 시작</h3>
                  <p className='text-muted-foreground text-[12px] mb-3'>
                    등록된 계정을 선택하고 워밍업 Day를 선택해서 시작하세요
                  </p>
                  <div className='flex flex-wrap items-center gap-3 mb-4'>
                    <Select value={warmupDay} onValueChange={setWarmupDay}>
                      <SelectTrigger className='w-32'>
                        <SelectValue placeholder='Day 선택' />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value='1'>Day 1</SelectItem>
                        <SelectItem value='2'>Day 2</SelectItem>
                        <SelectItem value='3'>Day 3</SelectItem>
                      </SelectContent>
                    </Select>
                    <span className='text-muted-foreground text-[12px]'>{warmupDayDescs[warmupDay]}</span>
                  </div>
                  <div className='flex items-center gap-3'>
                    <Button
                      disabled={warmupSelected.length === 0 || warmupLoading}
                      onClick={async () => {
                        setWarmupLoading(true)
                        setWarmupMsg('')
                        try {
                          await fetchApi('/api/tasks/warmup/batch', {
                            method: 'POST',
                            body: JSON.stringify({ account_ids: warmupSelected, day: parseInt(warmupDay) }),
                          })
                          setWarmupMsg(`${warmupSelected.length}개 계정 워밍업 Day ${warmupDay} 시작됨`)
                          setWarmupSelected([])
                        } catch {
                          setWarmupMsg('워밍업 시작 실패')
                        } finally {
                          setWarmupLoading(false)
                        }
                      }}
                      className='hydra-btn-press'
                    >
                      {warmupLoading ? '실행 중...' : `워밍업 시작 (${warmupSelected.length}개)`}
                    </Button>
                    {warmupMsg && <span className='text-muted-foreground text-[12px]'>{warmupMsg}</span>}
                  </div>
                </div>

                {/* Warmup candidates table */}
                <div className='overflow-x-auto'>
                  <table className='w-full text-sm'>
                    <thead>
                      <tr className='border-b border-border'>
                        <th className='w-10 p-3'>
                          <Checkbox
                            checked={warmupCandidates.length > 0 && warmupSelected.length === warmupCandidates.length}
                            onCheckedChange={checked => setWarmupSelected(checked ? warmupCandidates.map(a => a.id) : [])}
                          />
                        </th>
                        <th className='p-3 text-left font-medium text-[12px] text-muted-foreground'>계정명</th>
                        <th className='p-3 text-center font-medium text-[12px] text-muted-foreground'>상태</th>
                        <th className='p-3 text-right font-medium text-[12px] text-muted-foreground'>마지막 활동</th>
                      </tr>
                    </thead>
                    <tbody>
                      {warmupCandidates.length === 0 ? (
                        <tr>
                          <td colSpan={4} className='py-12 text-center text-muted-foreground text-[13px]'>
                            워밍업 대상 계정이 없어요. 등록된 계정만 표시됩니다.
                          </td>
                        </tr>
                      ) : warmupCandidates.map(acc => (
                        <tr key={acc.id} className='border-b border-border/30 hydra-row-hover'>
                          <td className='p-3'>
                            <Checkbox
                              checked={warmupSelected.includes(acc.id)}
                              onCheckedChange={checked => setWarmupSelected(prev => checked ? [...prev, acc.id] : prev.filter(id => id !== acc.id))}
                            />
                          </td>
                          <td className='p-3'>
                            <div className='flex items-center gap-2'>
                              <span className={`inline-block h-2 w-2 rounded-full ${statusDot[acc.status] || 'bg-gray-500'}`} />
                              <span className='text-[13px]'>{acc.gmail}</span>
                            </div>
                          </td>
                          <td className='p-3 text-center'>
                            <span className={`hydra-tag ${statusTagClass[acc.status] || 'hydra-tag-muted'}`}>
                              {statusLabels[acc.status] || acc.status}
                            </span>
                          </td>
                          <td className='p-3 text-right text-muted-foreground text-[12px]'>
                            {acc.last_active_at ? new Date(acc.last_active_at).toLocaleString('ko') : '-'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </TabsContent>

            <TabsContent value='problem' className='mt-4'>
              {renderTable(problemAccounts)}
            </TabsContent>
          </Tabs>

          <AccountDetailSheet
            accountId={selectedAccountId}
            open={sheetOpen}
            onOpenChange={setSheetOpen}
          />
        </div>
      </Main>
    </>
  )
}
