import { createFileRoute } from '@tanstack/react-router'
import { AuditCommex } from '@/features/audit-commex'

export const Route = createFileRoute('/_authenticated/audit/')({
  component: AuditCommex,
})
