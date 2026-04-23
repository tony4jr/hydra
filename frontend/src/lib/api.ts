import axios, { type AxiosRequestConfig } from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

// 단일 axios 인스턴스 — 전역 공용. 모든 API 호출이 이 인터셉터 체인을 지남.
// 내부 axios 인스턴스. 외부에서 multipart 등 필요 시 `http` 로 export 하여 쓸 수 있음
// (JWT 인터셉터 동일 적용).
export const http = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
})

// 요청 인터셉터: localStorage 의 JWT 를 Authorization 헤더에 자동 주입.
// 어드민 로그인(Phase 1b Task 18) 이후 프론트가 'hydra_token' 에 저장하면 자동 적용됨.
// 토큰 없으면 그냥 패스 (구 endpoint 호환).
http.interceptors.request.use((config) => {
  const token = localStorage.getItem('hydra_token')
  if (token) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 응답 인터셉터: 401 Unauthorized 면 토큰 제거 + 로그인 페이지 이동.
// 로그인 페이지 자체에서는 이 로직 발동 안 하도록 현재 경로 체크.
http.interceptors.response.use(
  (resp) => resp,
  (err) => {
    if (err.response?.status === 401) {
      const onLoginPage = window.location.pathname.startsWith('/login')
      if (!onLoginPage) {
        localStorage.removeItem('hydra_token')
        window.location.href = '/login'
      }
    }
    return Promise.reject(err)
  }
)

/**
 * 범용 API 호출 헬퍼.
 *
 * 시그니처는 기존 fetch 기반과 동일하게 유지 (기존 60+ 호출처 변경 불필요).
 * 내부적으로 axios 인스턴스 사용하여 JWT 자동 주입 + 401 처리.
 *
 * 사용 예:
 *   fetchApi<User>('/api/user/me')
 *   fetchApi('/api/user/update', { method: 'POST', body: JSON.stringify({name: 'x'}) })
 */
export async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const method = (options?.method || 'GET').toUpperCase()

  // RequestInit 의 body 는 string | FormData | URLSearchParams 등.
  // axios 는 data 필드로 받고, Content-Type 헤더 자동 설정.
  let data: unknown = undefined
  if (options?.body !== undefined && options.body !== null) {
    const body = options.body
    if (typeof body === 'string') {
      try {
        data = JSON.parse(body)
      } catch {
        data = body
      }
    } else {
      data = body
    }
  }

  const headersInit = options?.headers as Record<string, string> | undefined

  const axiosConfig: AxiosRequestConfig = {
    url: path,
    method,
    data,
    headers: {
      'Content-Type': 'application/json',
      ...(headersInit ?? {}),
    },
  }

  try {
    const resp = await http.request<T>(axiosConfig)
    return resp.data
  } catch (err) {
    if (axios.isAxiosError(err) && err.response) {
      throw new Error(`API error: ${err.response.status}`)
    }
    throw err
  }
}

// 참고: http 는 이미 최상단에서 export const 로 선언됨.
