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

// نگاشت کدهای دلیل تصمیم گیت به فارسی
export const reasonFa: Record<string, string> = {
  ALLOW: 'تردد مجاز',
  VEHICLE_NOT_REGISTERED: 'خودرو در سیستم ثبت نشده است',
  VEHICLE_INACTIVE: 'خودرو غیرفعال است',
  PLATE_INVALID: 'پلاک نامعتبر است',
  UNKNOWN_PLATE: 'پلاک ناشناس',
  NO_ACTIVE_PERMIT: 'مجوز فعالی برای این خودرو یافت نشد',
  PERMIT_NOT_FOUND: 'مجوزی یافت نشد',
  PERMIT_EXPIRED: 'اعتبار مجوز به پایان رسیده است',
  PERMIT_NOT_STARTED: 'مجوز هنوز شروع نشده است',
  PERMIT_INACTIVE: 'مجوز غیرفعال است',
  OUT_OF_TIME_WINDOW: 'خارج از بازه زمانی مجاز',
  ALLOWED_DAYS_MISMATCH: 'این روز برای تردد مجاز نیست',
  DAY_NOT_ALLOWED: 'این روز برای تردد مجاز نیست',
  MAX_ENTRIES_REACHED: 'سقف تعداد تردد پر شده است',
  VEHICLE_RESTRICTED: 'خودرو محدود/ممنوع است',
  RESTRICTION_ACTIVE: 'محدودیت فعال برای این خودرو ثبت است',
  VEHICLE_BANNED: 'تردد این خودرو ممنوع است',
  GATE_NOT_ALLOWED: 'این گیت برای این مجوز مجاز نیست',
  GATE_DIRECTION_NOT_ALLOWED: 'جهت تردد برای این مجوز مجاز نیست',
  SESSION_ALREADY_OPEN: 'جلسه پارکینگ قبلا باز است (ورود تکراری)',
  NO_OPEN_SESSION: 'جلسه بازی برای خروج یافت نشد',
  HAS_DEBT: 'بدهی پرداخت‌نشده وجود دارد',
  INSUFFICIENT_BALANCE: 'موجودی کافی نیست',
  REQUIRE_OPERATOR_APPROVAL: 'نیاز به تایید اپراتور',
  DUPLICATE_EVENT: 'رویداد تکراری',
  OFFLINE_ALLOW: 'تردد آفلاین مجاز',
  OFFLINE_REQUIRE_REVIEW: 'نیاز به بررسی (حالت آفلاین)',
  NO_OPEN_SESSION_FOR_EXIT: 'جلسه بازی برای خروج یافت نشد',
  EXIT_SESSION_CLOSED: 'جلسه پارکینگ در لحظه خروج بسته شد',
  DUPLICATE_ENTRY_SESSION_OPEN: 'ورود تکراری — جلسه پارکینگ از قبل باز است',
  PLATE_NOT_READABLE: 'پلاک قابل خواندن نیست',
  PLATE_RESTRICTED: 'این پلاک محدود/ممنوع است',
  VALID_PERMIT: 'مجوز معتبر',
  OFFLINE_DECISION_MISMATCH: 'اختلاف تصمیم آفلاین با سرور — نیازمند بررسی',
}
