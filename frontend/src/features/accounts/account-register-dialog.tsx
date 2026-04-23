import { useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogDescription,
  DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { fetchApi } from '@/lib/api'
import { toast } from 'sonner'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated?: () => void
}

export function AccountRegisterDialog({ open, onOpenChange, onCreated }: Props) {
  const [gmail, setGmail] = useState('')
  const [password, setPassword] = useState('')
  const [profileId, setProfileId] = useState('')
  const [recovery, setRecovery] = useState('')
  const [phone, setPhone] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (!gmail.trim() || !password || !profileId.trim()) {
      toast.error('필수 항목을 모두 입력하세요')
      return
    }
    setBusy(true)
    try {
      await fetchApi<{ account_id: number }>(
        '/api/admin/accounts/register',
        {
          method: 'POST',
          body: JSON.stringify({
            gmail: gmail.trim(),
            password,
            adspower_profile_id: profileId.trim(),
            recovery_email: recovery.trim() || null,
            phone_number: phone.trim() || null,
          }),
        },
      )
      toast.success('등록됨 · 온보딩 태스크 자동 생성')
      onCreated?.()
      onOpenChange(false)
      setGmail(''); setPassword(''); setProfileId('')
      setRecovery(''); setPhone('')
    } catch (e) {
      toast.error((e as Error).message || '등록 실패')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>계정 등록</DialogTitle>
          <DialogDescription>
            등록 즉시 온보딩 단계로 자동 진행됩니다 (M1).
          </DialogDescription>
        </DialogHeader>

        <div className='space-y-3'>
          <div>
            <Label>Gmail *</Label>
            <Input value={gmail} onChange={(e) => setGmail(e.target.value)} autoFocus />
          </div>
          <div>
            <Label>비밀번호 *</Label>
            <Input type='password' value={password}
                   onChange={(e) => setPassword(e.target.value)} />
          </div>
          <div>
            <Label>AdsPower Profile ID *</Label>
            <Input value={profileId}
                   onChange={(e) => setProfileId(e.target.value)}
                   placeholder='k1xxx' />
          </div>
          <div>
            <Label>복구 이메일</Label>
            <Input value={recovery}
                   onChange={(e) => setRecovery(e.target.value)} />
          </div>
          <div>
            <Label>전화번호</Label>
            <Input value={phone}
                   onChange={(e) => setPhone(e.target.value)}
                   placeholder='+82...' />
          </div>
        </div>

        <DialogFooter>
          <Button variant='outline'
                  onClick={() => onOpenChange(false)}
                  disabled={busy}>취소</Button>
          <Button onClick={submit} disabled={busy}>
            {busy ? '등록중…' : '등록'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
