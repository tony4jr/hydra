import { useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import axios from 'axios'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card } from '@/components/ui/card'
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

export function LoginPage() {
  const navigate = useNavigate()
  const [serverError, setServerError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

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
    <div className='flex min-h-screen items-center justify-center bg-muted/30 px-4'>
      <Card className='w-full max-w-sm p-6'>
        <div className='mb-6 text-center'>
          <h1 className='text-2xl font-semibold'>HYDRA</h1>
          <p className='mt-1 text-sm text-muted-foreground'>
            관리자 로그인
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
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            {serverError && (
              <p className='text-sm text-destructive' role='alert'>
                {serverError}
              </p>
            )}

            <Button type='submit' disabled={loading} className='mt-2'>
              {loading ? '로그인 중…' : '로그인'}
            </Button>
          </form>
        </Form>
      </Card>
    </div>
  )
}
