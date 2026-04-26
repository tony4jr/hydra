import { useState, useEffect } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import axios from 'axios'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormMessage,
} from '@/components/ui/form'

const schema = z.object({
  email: z.string().min(1, '이메일을 입력하세요'),
  password: z.string().min(1, '비밀번호를 입력하세요'),
})

type FormValues = z.infer<typeof schema>

/**
 * Login — operator's gate.
 *
 * Layout: full-bleed split. Left side: brand atmosphere with animated
 * orb + tagline. Right side: form.
 *
 * Mobile: brand collapses to a small badge above the form.
 */
export function LoginPage() {
  const navigate = useNavigate()
  const [serverError, setServerError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [time, setTime] = useState(new Date())

  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: '', password: '' },
  })

  const onSubmit = async (values: FormValues) => {
    setServerError(null)
    setLoading(true)
    try {
      const base = import.meta.env.VITE_API_BASE_URL || ''
      const resp = await axios.post(`${base}/api/admin/auth/login`, values)
      localStorage.setItem('hydra_token', resp.data.token)
      navigate({ to: '/' })
    } catch (e) {
      const detail =
        axios.isAxiosError(e) && e.response?.data?.detail
          ? String(e.response.data.detail)
          : '로그인에 실패했습니다'
      setServerError(detail)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className='hydra-login-shell'>
      {/* Left: brand panel */}
      <div className='hydra-login-brand'>
        <div className='hydra-login-orb hydra-login-orb-1' />
        <div className='hydra-login-orb hydra-login-orb-2' />
        <div className='hydra-login-orb hydra-login-orb-3' />

        <div className='relative z-10'>
          <div className='hydra-login-logo'>HYDRA</div>
          <div className='hydra-login-tag'>
            의도된 댓글, 자연스러운 영향력.
          </div>
          <ul className='hydra-login-bullets'>
            <li>· 50+ 계정 동시 운용 + IP 회전</li>
            <li>· AI 기반 댓글 + 시나리오 자동화</li>
            <li>· 실시간 함대 모니터링</li>
          </ul>
          <div className='hydra-login-clock'>
            {time.toLocaleString('ko-KR', {
              year: 'numeric', month: '2-digit', day: '2-digit',
              hour: '2-digit', minute: '2-digit', second: '2-digit',
              hour12: false,
            })}
          </div>
        </div>
      </div>

      {/* Right: form */}
      <div className='hydra-login-form-side'>
        <div className='hydra-login-card'>
          <div className='hydra-login-card-head'>
            <div className='hydra-login-badge'>
              <span className='hydra-login-pulse' />
              운영자 로그인
            </div>
            <h1 className='hydra-login-title'>안녕하세요, 다시 오셨네요</h1>
            <p className='hydra-login-sub'>
              자격증명을 입력해서 함대 콘솔에 접속하세요.
            </p>
          </div>

          <Form {...form}>
            <form
              onSubmit={form.handleSubmit(onSubmit)}
              className='flex flex-col gap-4'
              noValidate
            >
              <FormField
                control={form.control}
                name='email'
                render={({ field }) => (
                  <FormItem>
                    <Label htmlFor='email'>이메일</Label>
                    <FormControl>
                      <Input
                        id='email'
                        type='text'
                        autoComplete='username'
                        placeholder='admin@hydra.local'
                        autoFocus
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name='password'
                render={({ field }) => (
                  <FormItem>
                    <Label htmlFor='password'>비밀번호</Label>
                    <FormControl>
                      <Input
                        id='password'
                        type='password'
                        autoComplete='current-password'
                        placeholder='••••••••'
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {serverError && (
                <p className='hydra-login-error' role='alert'>
                  {serverError}
                </p>
              )}

              <Button
                type='submit'
                disabled={loading}
                className='hydra-btn-press hydra-login-submit mt-2'
              >
                {loading ? '인증 중…' : '입장'}
              </Button>
            </form>
          </Form>

          <div className='hydra-login-footer'>
            <span className='hydra-login-pulse-mini' />
            HYDRA Console — 운영팀 전용
          </div>
        </div>
      </div>
    </div>
  )
}
