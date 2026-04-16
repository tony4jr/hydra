import { createFileRoute } from '@tanstack/react-router'
import TargetsPage from '@/features/targets'

export const Route = createFileRoute('/_authenticated/targets/')({
  component: TargetsPage,
})
