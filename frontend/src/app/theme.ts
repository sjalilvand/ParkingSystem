import * as emotionCacheNS from '@emotion/cache'
import type { EmotionCache } from '@emotion/react'
import { prefixer } from 'stylis'
import rtlPlugin from 'stylis-plugin-rtl'
import { createTheme } from '@mui/material/styles'

type CacheFactory = (options: Record<string, unknown>) => EmotionCache
const ns = emotionCacheNS as unknown as { createCache?: CacheFactory; default?: CacheFactory }
const createCacheFn: CacheFactory = ns.createCache ?? ns.default!

export const rtlCache: EmotionCache = createCacheFn({
  key: 'muirtl',
  stylisPlugins: [prefixer, rtlPlugin],
})

export const theme = createTheme({
  direction: 'rtl',
  palette: {
    primary: { main: '#1565C0' },
    secondary: { main: '#00897B' },
    success: { main: '#2E7D32' },
    warning: { main: '#F57C00' },
    error: { main: '#C62828' },
    background: { default: '#F0F4F8' },
  },
  shape: { borderRadius: 14 },
  typography: { fontFamily: "'Vazirmatn', Vazir, Tahoma, sans-serif" },
  components: {
    MuiAppBar: {
      styleOverrides: {
        root: { background: 'linear-gradient(90deg, #0D47A1 0%, #1976D2 60%, #1E88E5 100%)' },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: { borderRadius: 16, boxShadow: '0 2px 14px rgba(16, 42, 83, 0.08)' },
      },
    },
    MuiButton: {
      styleOverrides: { root: { borderRadius: 12, minHeight: 42, fontWeight: 700 } },
    },
  },
})

export const decisionColors: Record<string, string> = {
  ALLOW: '#2E7D32',
  ALLOW_WITH_WARNING: '#F9A825',
  REQUIRE_OPERATOR_APPROVAL: '#F9A825',
  OFFLINE_ALLOW: '#2E7D32',
  OFFLINE_REQUIRE_REVIEW: '#F9A825',
  DENY: '#C62828',
  UNKNOWN_PLATE: '#C62828',
}

export const decisionFa: Record<string, string> = {
  ALLOW: 'مجاز',
  ALLOW_WITH_WARNING: 'مجاز با هشدار',
  REQUIRE_OPERATOR_APPROVAL: 'نیاز به تأیید اپراتور',
  OFFLINE_ALLOW: 'مجاز (آفلاین)',
  OFFLINE_REQUIRE_REVIEW: 'نیاز به بررسی (آفلاین)',
  DENY: 'ممنوع',
  UNKNOWN_PLATE: 'پلاک ناشناس',
}