import { createFileRoute } from '@tanstack/react-router'
import NicheLayout from '@/features/products/niche-layout'

export const Route = createFileRoute('/_authenticated/products/$brandId/niches/$nicheId')({
  component: NicheLayout,
})
