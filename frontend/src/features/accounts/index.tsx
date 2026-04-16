import { useEffect, useState } from 'react'
import {
  Users,
  CheckCircle2,
  Flame,
  Snowflake,
  ShieldOff,
  Ghost,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { fetchApi } from '@/lib/api'

interface Account {
  id: number
  name: string
  status: string
  current_pc: string | null
  today_tasks: number
  success_rate: number
  last_activity: string | null
}

interface AccountStats {
  total: number
  active: number
  warmup: number
  cooldown: number
  retired: number
  ghost: number
}

const statusColor = (s: string) => {
  switch (s) {
    case 'active':
      return 'default' as const
    case 'warmup':
      return 'secondary' as const
    case 'cooldown':
      return 'outline' as const
    case 'retired':
      return 'destructive' as const
    case 'ghost':
      return 'secondary' as const
    default:
      return 'secondary' as const
  }
}

const statusDotColor = (s: string) => {
  switch (s) {
    case 'active':
      return 'bg-green-500'
    case 'warmup':
      return 'bg-yellow-500'
    case 'cooldown':
      return 'bg-blue-500'
    case 'retired':
      return 'bg-red-500'
    case 'ghost':
      return 'bg-orange-500'
    default:
      return 'bg-gray-500'
  }
}

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[]>([])
  const [stats, setStats] = useState<AccountStats>({
    total: 0,
    active: 0,
    warmup: 0,
    cooldown: 0,
    retired: 0,
    ghost: 0,
  })

  useEffect(() => {
    fetchApi<AccountStats>('/accounts/api/stats')
      .then(setStats)
      .catch(() => {})
    fetchApi<{ items: Account[] }>('/accounts/api/list')
      .then((data) => setAccounts(data.items || []))
      .catch(() => {})
  }, [])

  const statCards = [
    { title: '전체', value: stats.total, icon: Users, color: 'text-muted-foreground' },
    { title: '활성', value: stats.active, icon: CheckCircle2, color: 'text-green-500' },
    { title: '워밍업', value: stats.warmup, icon: Flame, color: 'text-yellow-500' },
    { title: '쿨다운', value: stats.cooldown, icon: Snowflake, color: 'text-blue-500' },
    { title: '정지', value: stats.retired, icon: ShieldOff, color: 'text-red-500' },
    { title: '고스트', value: stats.ghost, icon: Ghost, color: 'text-orange-500' },
  ]

  const accountTable = (items: Account[]) => (
    <Card>
      <CardContent className='p-0'>
        <div className='overflow-auto'>
          <table className='w-full text-sm'>
            <thead>
              <tr className='border-b bg-muted/50'>
                <th className='p-3 text-left font-medium'>계정명</th>
                <th className='p-3 text-center font-medium'>상태</th>
                <th className='p-3 text-center font-medium'>현재 PC</th>
                <th className='p-3 text-center font-medium'>오늘 작업</th>
                <th className='p-3 text-center font-medium'>성공률</th>
                <th className='p-3 text-right font-medium'>마지막 활동</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr>
                  <td
                    colSpan={6}
                    className='p-10 text-center text-muted-foreground'
                  >
                    등록된 계정이 없습니다. 서버 연결 후 표시됩니다.
                  </td>
                </tr>
              ) : (
                items.map((acc) => (
                  <tr
                    key={acc.id}
                    className='cursor-pointer border-b hover:bg-muted/50'
                  >
                    <td className='p-3'>
                      <div className='flex items-center gap-2'>
                        <span
                          className={`inline-block h-2 w-2 rounded-full ${statusDotColor(acc.status)}`}
                        />
                        {acc.name}
                      </div>
                    </td>
                    <td className='p-3 text-center'>
                      <Badge variant={statusColor(acc.status)}>
                        {acc.status}
                      </Badge>
                    </td>
                    <td className='p-3 text-center'>
                      {acc.current_pc || (
                        <span className='text-muted-foreground'>-</span>
                      )}
                    </td>
                    <td className='p-3 text-center'>{acc.today_tasks}</td>
                    <td className='p-3 text-center'>{acc.success_rate}%</td>
                    <td className='p-3 text-right text-muted-foreground'>
                      {acc.last_activity
                        ? new Date(acc.last_activity).toLocaleString('ko')
                        : '-'}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
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
        <div className='mb-2 flex flex-wrap items-center justify-between space-y-2'>
          <div>
            <h2 className='text-2xl font-bold tracking-tight'>계정</h2>
            <p className='text-muted-foreground'>
              YouTube 계정 상태 및 건강도 관리
            </p>
          </div>
        </div>

        {/* Stat cards */}
        <div className='mb-6 grid gap-4 sm:grid-cols-3 lg:grid-cols-6'>
          {statCards.map((card) => (
            <Card
              key={card.title}
              className='cursor-pointer transition-colors hover:border-primary'
            >
              <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
                <CardTitle className='text-sm font-medium'>
                  {card.title}
                </CardTitle>
                <card.icon className={`h-4 w-4 ${card.color}`} />
              </CardHeader>
              <CardContent>
                <div className='text-2xl font-bold'>{card.value}</div>
              </CardContent>
            </Card>
          ))}
        </div>

        <Tabs defaultValue='all'>
          <TabsList>
            <TabsTrigger value='all'>전체 계정</TabsTrigger>
            <TabsTrigger value='warmup'>워밍업</TabsTrigger>
            <TabsTrigger value='problem'>문제 계정</TabsTrigger>
            <TabsTrigger value='profiles'>프로필 풀</TabsTrigger>
          </TabsList>
          <TabsContent value='all' className='mt-4'>
            {accountTable(accounts)}
          </TabsContent>
          <TabsContent value='warmup' className='mt-4'>
            {accountTable(accounts.filter((a) => a.status === 'warmup'))}
          </TabsContent>
          <TabsContent value='problem' className='mt-4'>
            {accountTable(
              accounts.filter(
                (a) => a.status === 'retired' || a.status === 'ghost'
              )
            )}
          </TabsContent>
          <TabsContent value='profiles' className='mt-4'>
            <Card>
              <CardContent className='flex h-[300px] items-center justify-center'>
                <p className='text-muted-foreground'>
                  프로필 풀 관리 (구현 예정)
                </p>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </Main>
    </>
  )
}
