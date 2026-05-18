import {
  Home,
  Zap,
  RefreshCw,
  ListTodo,
  Video,
  Layers,
  BarChart3,
  Puzzle,
  Users,
  Cpu,
  ScrollText,
  Settings,
  Command,
  Eye,
} from 'lucide-react'
import { type SidebarData } from '../types'

/**
 * Commex Renewal IA — renewal_spec §2 / §3.2
 * 라우트는 hydra 기존 라우트 유지 (renewal_spec §5 가이드 준수).
 */
export const sidebarData: SidebarData = {
  user: {
    name: 'HYDRA Admin',
    email: 'admin@hydra.bot',
    avatar: '/avatars/01.png',
  },
  teams: [
    {
      name: 'Commex',
      logo: Command,
      plan: '댓글 운영 자동화',
    },
  ],
  navGroups: [
    {
      title: '메인',
      items: [
        { title: '홈', url: '/', icon: Home },
        { title: '빠른 작업', url: '/quick', icon: Zap },
        { title: '자동 작업', url: '/campaigns', icon: RefreshCw },
        { title: '작업 큐', url: '/queue', icon: ListTodo },
        { title: '영상 풀', url: '/videos', icon: Video },
        { title: '브랜드 / 니치', url: '/brands', icon: Layers },
        { title: '리포트', url: '/analytics', icon: BarChart3 },
      ],
    },
    {
      title: '관리자',
      items: [
        { title: '글로벌 프리셋', url: '/presets', icon: Puzzle },
        { title: '계정 · 아바타', url: '/accounts', icon: Users },
        { title: '워커', url: '/workers', icon: Cpu },
        { title: 'Screen Review', url: '/screen-review', icon: Eye },
        { title: '로그', url: '/audit', icon: ScrollText },
        { title: '전역 설정', url: '/settings', icon: Settings },
      ],
    },
  ],
}
