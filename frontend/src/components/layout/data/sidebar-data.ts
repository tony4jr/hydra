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
  UserCog,
  Wrench,
  Palette,
  Bell,
  Command,
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
      title: '운영',
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
      title: '관리',
      items: [
        {
          title: '계정',
          url: '/accounts',
          icon: Users,
        },
        {
          title: '워커',
          url: '/workers',
          icon: Monitor,
        },
        {
          title: '설정',
          icon: Settings,
          items: [
            {
              title: '프로필',
              url: '/settings',
              icon: UserCog,
            },
            {
              title: '계정 설정',
              url: '/settings/account',
              icon: Wrench,
            },
            {
              title: '외관',
              url: '/settings/appearance',
              icon: Palette,
            },
            {
              title: '알림',
              url: '/settings/notifications',
              icon: Bell,
            },
            {
              title: '디스플레이',
              url: '/settings/display',
              icon: Monitor,
            },
          ],
        },
      ],
    },
  ],
}
