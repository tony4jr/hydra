import { createFileRoute } from '@tanstack/react-router'
import BrandDetailPage from '@/features/products/brand-detail'

export const Route = createFileRoute('/_authenticated/brands/$brandId/')({
  component: BrandDetailPage,
})
