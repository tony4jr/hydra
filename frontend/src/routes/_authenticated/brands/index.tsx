import { createFileRoute } from '@tanstack/react-router'
import { BrandsCommex } from '@/features/brands-commex'

export const Route = createFileRoute('/_authenticated/brands/')({
  component: BrandsCommex,
})
