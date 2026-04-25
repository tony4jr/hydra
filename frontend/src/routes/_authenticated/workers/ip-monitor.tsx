import { createFileRoute } from '@tanstack/react-router'
import IpMonitorPage from '@/features/workers/ip-monitor-page'

export const Route = createFileRoute('/_authenticated/workers/ip-monitor')({
  component: IpMonitorPage,
})
