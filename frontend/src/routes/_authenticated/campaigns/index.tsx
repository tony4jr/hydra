import { createFileRoute } from '@tanstack/react-router'
import { CampaignsCommex } from '@/features/campaigns-commex'

export const Route = createFileRoute('/_authenticated/campaigns/')({
  component: CampaignsCommex,
})
