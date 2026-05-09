import { createFileRoute } from '@tanstack/react-router'
import { AccountsCommex } from '@/features/accounts-commex'

export const Route = createFileRoute('/_authenticated/accounts/')({
  component: AccountsCommex,
})
