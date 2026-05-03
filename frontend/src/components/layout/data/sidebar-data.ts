import {
  LayoutDashboard,
  ListTodo,
  Users,
  Video,
  Monitor,
  Settings,
  Command,
  ScrollText,
  Boxes,
  Sparkles,
  Activity,
  AlertTriangle,
  ListChecks,
} from 'lucide-react'
import { type SidebarData } from '../types'

/**
 * PR-8a 사이드바 IA — 3 그룹 (지금/자산/안전).
 *
 * 신규 페이지 (피드/문제/예정/프리셋/키워드) 는 PR-8b 등 후속 sub-PR 에서 추가.
 * 본 PR-8a 는 현재 존재하는 페이지의 그룹/순서 재배치 + rename 만.
 */
export const sidebarData: SidebarData = {
  user: {
    name: 'HYDRA Admin',
    email: 'admin@hydra.bot',
    avatar: '/avatars/01.png',
  },
  teams: [
    {
      name: 'HYDRA',
      logo: Command,
      plan: 'YouTube Marketing Bot',
    },
  ],
  navGroups: [
    {
      title: '지금',
      items: [
        {
          title: '피드',
          url: '/feed',
          icon: Activity,
        },
        {
          title: '문제',
          url: '/alerts',
          icon: AlertTriangle,
        },
        {
          title: '예정',
          url: '/queue',
          icon: ListTodo,
        },
        {
          title: '대시보드',
          url: '/',
          icon: LayoutDashboard,
        },
        {
          title: '시작하기',
          url: '/onboarding',
          icon: Sparkles,
        },
      ],
    },
    {
      title: '운영',
      items: [
        {
          title: '브랜드',
          url: '/brands',
          icon: Boxes,
        },
        {
          title: '프리셋',
          url: '/presets',
          icon: ListChecks,
        },
        {
          title: '영상',
          url: '/videos',
          icon: Video,
        },
      ],
    },
    {
      title: '계정',
      items: [
        {
          title: '계정 · 아바타',
          url: '/accounts',
          icon: Users,
        },
      ],
    },
    {
      title: '안전',
      items: [
        {
          title: '워커',
          url: '/workers',
          icon: Monitor,
        },
        {
          title: '로그',
          url: '/audit',
          icon: ScrollText,
        },
        {
          title: '설정',
          url: '/settings',
          icon: Settings,
        },
      ],
    },
  ],
}
