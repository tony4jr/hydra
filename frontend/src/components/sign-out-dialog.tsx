import { useNavigate } from '@tanstack/react-router'
import { toast } from 'sonner'
import axios from 'axios'
import { ConfirmDialog } from '@/components/confirm-dialog'

interface SignOutDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function SignOutDialog({ open, onOpenChange }: SignOutDialogProps) {
  const navigate = useNavigate()

  const handleSignOut = () => {
    // 1. Clear client-side credentials FIRST (so guard kicks in immediately)
    localStorage.removeItem('hydra_token')
    sessionStorage.clear()
    // 2. Server-side logout (fire-and-forget, 3s timeout — never blocks redirect)
    try {
      const base = import.meta.env.VITE_API_BASE_URL || ''
      const token = localStorage.getItem('hydra_token')
      axios.post(
        `${base}/api/admin/auth/logout`,
        {},
        {
          timeout: 3000,
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        },
      ).catch(() => { /* ignore */ })
    } catch {
      /* ignore */
    }
    // 3. Close dialog + toast + hard redirect (full reload resets all queries)
    onOpenChange(false)
    toast.success('로그아웃됨')
    window.location.href = '/login'
    setTimeout(() => navigate({ to: '/login' }), 100)
  }

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title='로그아웃'
      desc='정말 로그아웃 하시겠어요?'
      confirmText='로그아웃'
      destructive
      handleConfirm={handleSignOut}
      className='sm:max-w-sm'
    />
  )
}
