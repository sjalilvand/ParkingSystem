import axios from 'axios'

export const tokens: { access: string; refresh: string } = { access: '', refresh: '' }

export const api = axios.create({ baseURL: '/api/v1' })

api.interceptors.request.use((cfg) => {
  if (tokens.access) cfg.headers.Authorization = `Bearer ${tokens.access}`
  return cfg
})

let refreshing: Promise<void> | null = null

api.interceptors.response.use(undefined, async (error) => {
  const original = error.config
  if (error.response?.status === 401 && tokens.refresh && !original._retry) {
    original._retry = true
    try {
      refreshing = refreshing ?? axios
        .post('/api/v1/auth/refresh', { refresh_token: tokens.refresh })
        .then((r) => {
          tokens.access = r.data.access_token
          tokens.refresh = r.data.refresh_token
        })
        .finally(() => { refreshing = null })
      await refreshing
      return api(original)
    } catch {
      tokens.access = ''
      tokens.refresh = ''
      window.location.href = '/login'
    }
  }
  return Promise.reject(error)
})

export function apiErrorFa(err: unknown): string {
  const e = err as {
    response?: { data?: { error?: { message?: string }; detail?: string }; status?: number }
    message?: string
  }
  if (e?.response?.data?.error?.message) return e.response.data.error.message
  if (e?.response?.data?.detail) return String(e.response.data.detail)
  if (e?.response?.status) return `خطا ${e.response.status} از سرور`
  // پیام عمدی پرتاب‌شده در کد (مثل: «این فایل ورودی است نه خروجی»)
  if (e?.message && e.message.length > 3 && e.message.length < 500 && e.message !== 'Network Error') {
    return e.message
  }
  return 'خطای شبکه — سرور در دسترس نیست'
}