// سرویس‌ورکر حذف شد — این نسخه فقط برای پاک‌سازی نسخه‌های قبلی روی مرورگرهای
// قدیمی است: همهٔ کش‌ها را حذف و خودش را لغو‌ثبت می‌کند، سپس صفحه را تازه می‌کند.
self.addEventListener("install", (event) => {
  event.waitUntil(self.skipWaiting())
})

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.map((k) => caches.delete(k))))
      .then(() => self.registration.unregister())
      .then(() => self.clients.matchAll({ type: "window" }))
      .then((clients) => clients.forEach((c) => {
        if ("navigate" in c) c.navigate(c.url)
      }))
  )
})

self.addEventListener("fetch", () => {
  // هیچ مداخله‌ای — درخواست‌ها مستقیم به شبکه می‌روند
})
