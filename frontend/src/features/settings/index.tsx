import { Outlet } from '@tanstack/react-router'
import { Palette, Wrench, ListChecks, Settings2 } from 'lucide-react'
import { Separator } from '@/components/ui/separator'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { SidebarNav } from './components/sidebar-nav'

const sidebarNavItems = [
  {
    title: '일반',
    href: '/settings',
    icon: <Wrench size={18} />,
  },
  {
    title: '행동 패턴',
    href: '/settings/behavior',
    icon: <Settings2 size={18} />,
  },
  {
    title: '프리셋',
    href: '/settings/presets',
    icon: <ListChecks size={18} />,
  },
  {
    title: '외관',
    href: '/settings/appearance',
    icon: <Palette size={18} />,
  },
]

export function Settings() {
  return (
    <>
      <Header>
        <div className='ml-auto flex items-center space-x-4'>
          <ThemeSwitch />
          <ProfileDropdown />
        </div>
      </Header>

      <Main fixed>
        <div className='space-y-0.5'>
          <h1 className='hydra-page-h'>설정</h1>
          <p className='hydra-page-sub'>
            API 키, 행동 패턴, 프리셋 등 HYDRA 설정을 관리합니다
          </p>
        </div>
        <Separator className='my-4 lg:my-6' />
        <div className='flex flex-1 flex-col space-y-2 overflow-hidden md:space-y-2 lg:flex-row lg:space-y-0 lg:space-x-12'>
          <aside className='top-0 lg:sticky lg:w-1/5'>
            <SidebarNav items={sidebarNavItems} />
          </aside>
          <div className='flex w-full overflow-y-hidden p-1'>
            <Outlet />
          </div>
        </div>
      </Main>
    </>
  )
}
