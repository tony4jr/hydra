import { Construction } from 'lucide-react'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { ThemeSwitch } from '@/components/theme-switch'

interface PlaceholderPageProps {
  title: string
  description?: string
}

export function PlaceholderPage({ title, description }: PlaceholderPageProps) {
  return (
    <>
      <Header>
        <div className='ms-auto flex items-center space-x-4'>
          <Search />
          <ThemeSwitch />
          <ProfileDropdown />
        </div>
      </Header>

      <Main>
        <div className='mb-2 flex items-center justify-between space-y-2'>
          <h1 className='text-2xl font-bold tracking-tight'>{title}</h1>
        </div>
        <div className='flex flex-col items-center justify-center rounded-lg border border-dashed p-12'>
          <Construction className='mb-4 h-12 w-12 text-muted-foreground' />
          <h2 className='text-lg font-semibold text-muted-foreground'>
            {description ?? `${title} 페이지는 개발 중입니다`}
          </h2>
          <p className='mt-2 text-sm text-muted-foreground'>
            이 페이지는 곧 구현될 예정입니다.
          </p>
        </div>
      </Main>
    </>
  )
}
