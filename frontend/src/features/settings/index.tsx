import { Outlet } from '@tanstack/react-router'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'

export function Settings() {
  return (
    <>
      <Header>
        <div className='ml-auto flex items-center space-x-4'>
          <ThemeSwitch />
          <ProfileDropdown />
        </div>
      </Header>

      <Main>
        <div className='space-y-0.5 mb-6'>
          <h1 className='hydra-page-h'>전역 설정</h1>
          <p className='hydra-page-sub'>
            API 키, 서버 정보, 알림 채널 등을 관리합니다.
          </p>
        </div>
        <Outlet />
      </Main>
    </>
  )
}
