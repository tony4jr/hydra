import { createFileRoute } from '@tanstack/react-router'
import OnboardingPage from '@/features/onboarding'

export const Route = createFileRoute('/_authenticated/onboarding/')({
  component: OnboardingPage,
})
