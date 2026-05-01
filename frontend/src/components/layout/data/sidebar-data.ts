import {
  LayoutDashboard,
  ListTodo,
  Users,
  Video,
  Monitor,
  Settings,
  Command,
  Image,
  ScrollText,
  Boxes,
  Sparkles,
} from 'lucide-react'
import { type SidebarData } from '../types'

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
      title: '홈',
      items: [
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
        {
          title: '작업',
          url: '/tasks',
          icon: ListTodo,
        },
      ],
    },
    {
      title: '제품 운영',
      items: [
        {
          title: '제품',
          url: '/products',
          icon: Boxes,
        },
        {
          title: '영상',
          url: '/videos',
          icon: Video,
        },
        {
          title: '계정',
          url: '/accounts',
          icon: Users,
        },
        {
          title: '아바타',
          url: '/avatars',
          icon: Image,
        },
      ],
    },
    {
      title: '인프라',
      items: [
        {
          title: '워커',
          url: '/workers',
          icon: Monitor,
        },
        {
          title: '감사 로그',
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
