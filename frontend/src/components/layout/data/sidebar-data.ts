import {
  LayoutDashboard,
  Tag,
  Video,
  Megaphone,
  ListTodo,
  BarChart3,
  Users,
  Monitor,
  Settings,
  Wrench,
  Palette,
  ListChecks,
  Settings2,
  Command,
  Image,
  ScrollText,
  Boxes,
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
          title: '브랜드',
          url: '/brands',
          icon: Tag,
        },
        {
          title: '타겟',
          url: '/targets',
          icon: Video,
        },
        {
          title: '캠페인',
          url: '/campaigns',
          icon: Megaphone,
        },
        {
          title: '작업',
          url: '/tasks',
          icon: ListTodo,
        },
        {
          title: '분석',
          url: '/analytics',
          icon: BarChart3,
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
          icon: Monitor,
          items: [
            { title: '목록', url: '/workers' },
            { title: '에러 로그', url: '/workers/errors' },
            { title: 'IP 감시', url: '/workers/ip-monitor' },
          ],
        },
        {
          title: '감사 로그',
          url: '/audit',
          icon: ScrollText,
        },
        {
          title: '설정',
          icon: Settings,
          items: [
            {
              title: '일반',
              url: '/settings',
              icon: Wrench,
            },
            {
              title: '행동 패턴',
              url: '/settings/behavior',
              icon: Settings2,
            },
            {
              title: '프리셋',
              url: '/settings/presets',
              icon: ListChecks,
            },
            {
              title: '외관',
              url: '/settings/appearance',
              icon: Palette,
            },
          ],
        },
      ],
    },
  ],
}
