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

  const handleSignOut = async () => {
    // 1. Server-side logout (best-effort — stateless JWT, server just no-ops)
    try {
      const base = import.meta.env.VITE_API_BASE_URL || ''
      const token = localStorage.getItem('hydra_token')
      await axios.post(
        `${base}/api/admin/auth/logout`,
        {},
        token ? { headers: { Authorization: `Bearer ${token}` } } : undefined,
      )
    } catch {
      /* server may be down or token expired — proceed anyway */
    }
    // 2. Clear client-side credentials
    localStorage.removeItem('hydra_token')
    sessionStorage.clear()
    // 3. Close dialog + redirect
    onOpenChange(false)
    toast.success('로그아웃됨')
    // Use full-page navigation so any in-flight queries also reset
    window.location.assign('/login')
    // (fallback if window.location is intercepted)
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
