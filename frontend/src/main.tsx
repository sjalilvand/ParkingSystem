 import '@fontsource/vazirmatn/arabic-400.css'
import '@fontsource/vazirmatn/arabic-700.css'
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './app/App'
import { Providers } from './app/providers'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Providers>
      <App />
    </Providers>
  </React.StrictMode>,
)

// سرویس‌ورکر به‌کلی حذف شد — عامل نمایش نسخهٔ قدیمی برنامه پس از هر استقرار بود.
// این پاک‌سازی یک‌باره، ثبت‌نام‌های قبلی و کش‌هایش را از مرورگر حذف می‌کند.
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.getRegistrations()
    .then((rs) => Promise.all(rs.map((r) => r.unregister())))
    .catch(() => {})
  if ('caches' in window) {
    caches.keys().then((keys) => Promise.all(keys.map((k) => caches.delete(k)))).catch(() => {})
  }
}