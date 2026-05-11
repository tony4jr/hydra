import { createFileRoute } from '@tanstack/react-router'
import { NichePresetEdit } from '@/features/niche-preset-edit'

export const Route = createFileRoute(
  '/_authenticated/brands/$brandId/niches/$nicheId/preset-edit'
)({
  component: NichePresetEdit,
})
