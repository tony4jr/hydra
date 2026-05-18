import { createFileRoute } from '@tanstack/react-router'
import ScreenReviewPage from '@/features/screen-review'

export const Route = createFileRoute('/_authenticated/screen-review')({
  component: ScreenReviewPage,
})
