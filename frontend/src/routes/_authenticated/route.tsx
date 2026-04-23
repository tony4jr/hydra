import { createFileRoute, redirect } from '@tanstack/react-router'
import { AuthenticatedLayout } from '@/components/layout/authenticated-layout'

export const Route = createFileRoute('/_authenticated')({
  beforeLoad: ({ location }) => {
    // Task 27: 토큰 없으면 로그인 페이지로. api.ts 의 401 인터셉터와 이중 방어.
    const token =
      typeof window !== 'undefined' ? localStorage.getItem('hydra_token') : null
    if (!token) {
      throw redirect({
        to: '/login',
        search: { redirect: location.href },
      })
    }
  },
  component: AuthenticatedLayout,
})
