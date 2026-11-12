import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * v2.7.0 — ابزارهای «کارکرد بی‌وقفه» صفحهٔ گیت.
 *
 * ریشهٔ گزارشِ «وقتی مدتی با سیستم کار نکنی، صفحه میره تو حالت استپ»:
 *   ۱) مرورگر (Chrome/Edge) تایمرهای tabِ پس‌زمینه را به‌شدت کند می‌کند و
 *      Edge بعد از مدت بی‌کاری، tab را کاملاً می‌خواباند (Sleeping Tabs) —
 *      تایمر داخل Web Worker از این قوانین معاف است.
 *   ۲) tabِ «در حال پخش صدا» هرگز به‌خواب نمی‌رود — یک صوتِ تقریباً بی‌صدا
 *      (دامنهٔ ۰٫۰۸٪) نگه می‌داریم تا صفحهٔ گیت تا ابد بیدار بماند.
 *   ۳) با Screen Wake Lock مانع خاموش‌شدن صفحهٔ سرور می‌شویم (وقتی مرئی است).
 */

/** تیکِ مقاوم در برابر خواب‌شدن tab — تایمر داخل Web Worker (معاف از throttle). */
export function useTickWorker(intervalMs = 3000): number {
  const [tick, setTick] = useState(0)
  useEffect(() => {
    let worker: Worker | null = null
    let fallback: ReturnType<typeof setInterval> | null = null
    try {
      const src =
        `let h=null;onmessage=(e)=>{` +
        `if(e.data==='start'&&!h){h=setInterval(()=>postMessage(1),${Math.max(250, intervalMs)})}` +
        `if(e.data==='stop'){clearInterval(h);h=null}};`
      const url = URL.createObjectURL(new Blob([src], { type: 'text/javascript' }))
      worker = new Worker(url)
      worker.onmessage = () => setTick((t) => t + 1)
      worker.postMessage('start')
    } catch {
      // مرورگر بدون Worker — تایمر معمولی (بهتر از هیچ)
      fallback = setInterval(() => setTick((x) => x + 1), intervalMs)
    }
    return () => {
      try { worker?.postMessage('stop'); worker?.terminate() } catch { /* ignore */ }
      if (fallback) clearInterval(fallback)
    }
  }, [intervalMs])
  return tick
}

interface AlwaysAwakeResult {
  awake: boolean
  wakeLockSupported: boolean
  requestAwake: () => void
  disable: () => void
}

/**
 * «بیدارماندن» صفحهٔ گیت: صوتِ بی‌صدا + Wake Lock.
 * مرورگر اجازهٔ صوت را معمولاً بعد از اولین کلیک کاربر می‌دهد؛ تا آن موقع
 * با اولین pointerdown دوباره تلاش می‌کنیم — اپراتور فقط یک کلیک لازم دارد.
 */
export function useAlwaysAwake(): AlwaysAwakeResult {
  const [awake, setAwake] = useState(false)
  const [wanted, setWanted] = useState(false)
  const ctxRef = useRef<AudioContext | null>(null)
  const lockRef = useRef<{ release: () => Promise<void> } | null>(null)

  const acquireWakeLock = useCallback(async () => {
    try {
      const nav = navigator as unknown as { wakeLock?: { request: (t: string) => Promise<{ release: () => Promise<void>; addEventListener: (e: string, cb: () => void) => void }> } }
      if (nav.wakeLock && !lockRef.current && document.visibilityState === 'visible') {
        const sent = await nav.wakeLock.request('screen')
        sent.addEventListener('release', () => { lockRef.current = null })
        lockRef.current = sent
      }
    } catch { /* Wake Lock اختیاری است */ }
  }, [])

  const startAudio = useCallback(async () => {
    try {
      if (!ctxRef.current) {
        const Ctx = (window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext)
        if (!Ctx) return
        const ctx = new Ctx()
        const len = ctx.sampleRate                 // بافر ۱ ثانیه‌ای
        const buf = ctx.createBuffer(1, len, ctx.sampleRate)
        const data = buf.getChannelData(0)
        // موجِ ۱۰۰ هرتز با دامنهٔ ۰٫۰۸٪ — عملاً نامحسوس ولی «صدا»ست برای مرورگر
        for (let i = 0; i < len; i++) {
          data[i] = Math.sin((2 * Math.PI * 100 * i) / ctx.sampleRate) * 0.0008
        }
        const src = ctx.createBufferSource()
        src.buffer = buf
        src.loop = true
        const gain = ctx.createGain()
        gain.gain.value = 0.0008
        src.connect(gain)
        gain.connect(ctx.destination)
        src.start()
        ctxRef.current = ctx
      }
      if (ctxRef.current.state === 'suspended') await ctxRef.current.resume()
    } catch { /* صوت با اولین کلیک کاربر ادامه می‌یابد */ }
  }, [])

  const enable = useCallback(async () => {
    await startAudio()
    await acquireWakeLock()
    setAwake(!!ctxRef.current || !!lockRef.current)
  }, [startAudio, acquireWakeLock])

  const requestAwake = useCallback(() => {
    setWanted(true)
    void enable()
  }, [enable])

  const disable = useCallback(() => {
    setWanted(false)
    try { ctxRef.current?.close() } catch { /* ignore */ }
    ctxRef.current = null
    try { lockRef.current?.release() } catch { /* ignore */ }
    lockRef.current = null
    setAwake(false)
  }, [])

  // اگر مرورگر صوت را معلق کرد، با اولین لمس/کلیک خودکار ادامه می‌دهیم
  useEffect(() => {
    if (!wanted) return
    const kick = () => { void enable() }
    document.addEventListener('pointerdown', kick)
    return () => document.removeEventListener('pointerdown', kick)
  }, [wanted, enable])

  // بازگشت به tab → Wake Lock دوباره گرفته شود
  useEffect(() => {
    const onVis = () => { if (wanted && document.visibilityState === 'visible') void enable() }
    document.addEventListener('visibilitychange', onVis)
    return () => document.removeEventListener('visibilitychange', onVis)
  }, [wanted, enable])

  useEffect(() => () => disable(), [disable])

  const wakeLockSupported = 'wakeLock' in navigator
  return { awake, wakeLockSupported, requestAwake, disable }
}

/** تازه‌سازی فوری هنگام بازگشت به tab — صفحهٔ پس‌زمینه‌ای که برمی‌گردد فریزده به نظر نرسد. */
export function useRefreshOnVisible(refresh: () => void): void {
  const cb = useRef(refresh)
  cb.current = refresh
  useEffect(() => {
    const onVis = () => { if (document.visibilityState === 'visible') cb.current() }
    document.addEventListener('visibilitychange', onVis)
    return () => document.removeEventListener('visibilitychange', onVis)
  }, [])
}
