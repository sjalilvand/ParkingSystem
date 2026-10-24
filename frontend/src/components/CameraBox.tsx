import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Alert, Box, Button, Chip, CircularProgress, Dialog, DialogActions,
  DialogContent, DialogTitle, IconButton, Snackbar,
  Stack, Switch, TextField, Typography, FormControlLabel,
} from '@mui/material'
import {
  Build as WrenchIcon, Close as CloseIcon,
  ContentCopy as CopyIcon, PhotoCamera as CaptureIcon, Videocam as CamIcon,
} from '@mui/icons-material'
import { api, apiErrorFa } from '../api/client'

const sideFa = (side: string) => (side === 'IN' ? 'ورود' : 'خروج')

interface SideCfg { rtsp: string; enabled: boolean; name?: string; gate_code?: string; direction?: string }
interface CameraCfg { poll_interval: number; ocr: boolean; sides: Record<string, SideCfg> }
interface SideStatus {
  enabled?: boolean; connected?: boolean; has_frame?: boolean
  last_frame_iso?: string; last_ocr_iso?: string; last_ocr_ms?: number
  last_plate?: string | null; last_plate_fa?: string | null; last_conf?: number
  events_sent?: number; last_error?: string | null; reconnects?: number
}

function toFa(n: number | string): string {
  return String(n).replace(/\d/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[Number(d)])
}

/** نمایش زندهٔ دوربین + وضعیت poller + عکس‌گرفتن + تنظیمات (سناریو A/B) */
export default function CameraBox({ side, gateKey }: { side: 'IN' | 'OUT'; gateKey: string }) {
  const [cfg, setCfg] = useState<CameraCfg | null>(null)
  const [status, setStatus] = useState<SideStatus | null>(null)
  const [tick, setTick] = useState(0)
  const [dialog, setDialog] = useState(false)
  const [busy, setBusy] = useState(false)
  const [capturing, setCapturing] = useState(false)
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)
  const [snack, setSnack] = useState('')
  const [testPreview, setTestPreview] = useState(false)
  const [draft, setDraft] = useState<{ rtsp: string; enabled: boolean }>({ rtsp: '', enabled: false })
  const [draftGlobal, setDraftGlobal] = useState<{ interval: string; ocr: boolean }>({ interval: '10', ocr: true })
  const alive = useRef(true)

  const camCfg = cfg?.sides?.[side]

  useEffect(() => {
    alive.current = true
    return () => { alive.current = false }
  }, [])

  // پیکربندی دوربین‌ها
  const loadCfg = useCallback(async () => {
    try {
      const r = await api.get('/camera/config')
      if (alive.current) setCfg(r.data)
    } catch { /* بدون پیکربندی — placeholder */ }
  }, [])
  useEffect(() => { loadCfg() }, [loadCfg])

  // وضعیت poller (هر ۵ ثانیه)
  useEffect(() => {
    const t = setInterval(async () => {
      try {
        const r = await api.get('/camera/poller-status')
        if (alive.current) setStatus((r.data?.sides?.[side] ?? {}) as SideStatus)
      } catch { /* بی‌اهمیت */ }
    }, 5000)
    return () => clearInterval(t)
  }, [side])

  // refresh تصویر زنده
  const live = !!(camCfg?.enabled && camCfg?.rtsp)
  useEffect(() => {
    const t = setInterval(() => { if (live) setTick((x) => x + 1) }, 3000)
    return () => clearInterval(t)
  }, [live])

  const openDialog = () => {
    setDraft({ rtsp: camCfg?.rtsp ?? '', enabled: !!camCfg?.enabled })
    setDraftGlobal({ interval: String(cfg?.poll_interval ?? 10), ocr: cfg?.ocr !== false })
    setMsg(null)
    setTestPreview(false)
    setDialog(true)
  }

  const _save = async () => {
    setBusy(true); setMsg(null)
    try {
      await api.put('/camera/config', {
        sides: { ...(cfg?.sides ?? {}), [side]: { ...(camCfg ?? {}), rtsp: draft.rtsp, enabled: draft.enabled } },
        poll_interval: Number(draftGlobal.interval) || 10, ocr: draftGlobal.ocr,
      })
      await loadCfg()
      return true
    } catch (err) {
      setMsg({ kind: 'err', text: apiErrorFa(err) })
      return false
    } finally { setBusy(false) }
  }

  const testCamera = async () => {
    const ok = await _save()   // تست روی مقدار جدید → اول ذخیره
    if (!ok) return
    setBusy(true); setMsg(null)
    try {
      const r = await api.post(`/camera/test/${side}`)
      setMsg({ kind: 'ok', text: r.data?.message ?? 'اتصال موفق بود' })
      setTestPreview(true)
    } catch (err) {
      setMsg({ kind: 'err', text: apiErrorFa(err) })
    } finally { setBusy(false) }
  }

  const save = async () => {
    const ok = await _save()
    if (ok) setMsg({ kind: 'ok', text: 'پیکربندی دوربین ذخیره شد ✔' })
  }

  const capture = async () => {
    setCapturing(true); setMsg(null)
    try {
      const r = await api.post(`/camera/capture-ocr/${side}?auto_emit=true`)
      const best = r.data?.chosen ?? r.data?.best
      if (r.data?.event) {
        const ev = r.data.event
        setMsg({
          kind: 'ok',
          text: `پلاک «${best?.persian || best?.system || '—'}» خوانده شد → تصمیم: ${ev.decision || '—'} / راهبند: ${ev.barrier_action === 'OPEN' ? 'باز شود' : 'بسته'}`,
        })
      } else if (best?.system) {
        setMsg({
          kind: 'ok',
          text: `پلاک خوانده شد: ${best.persian || best.system} (اطمینان ${toFa(Math.round((best.confidence || 0) * 100))}٪) — برای ثبت، دکمهٔ «ارسال رویداد دوربین» را بزنید`,
        })
        window.dispatchEvent(new CustomEvent('camera-plate', { detail: { side, plate: best.system } }))
      } else {
        setMsg({ kind: 'err', text: 'پلاکی در تصویر شناسایی نشد — زاویه/نور دوربین را بهبود دهید و مجدد تلاش کنید' })
      }
      setTick((x) => x + 1)
    } catch (err) {
      setMsg({ kind: 'err', text: apiErrorFa(err) })
    } finally { setCapturing(false) }
  }

  const anprUrl = `${window.location.origin}/api/v1/gate/events/anpr/${camCfg?.gate_code || `GATE-${side}-01`}/${camCfg?.direction || side}?api_key=${gateKey}`

  const imgSrc = live
    ? `/api/v1/camera/snapshot/${side}?t=${tick}&api_key=${encodeURIComponent(gateKey)}`
    : null

  return (
    <Box>
      <Box sx={{ mb: 1.5, borderRadius: 2, overflow: 'hidden', border: '2px solid #E3EAF2', position: 'relative', backgroundColor: '#0d1117' }}>
        {imgSrc ? (
          <img src={imgSrc} alt={`دوربین ${sideFa(side)}`}
            style={{ width: '100%', display: 'block', aspectRatio: '16/6', objectFit: 'cover' }}
            onError={(e) => { (e.target as HTMLImageElement).style.opacity = '0.25' }} />
        ) : (
          <Box sx={{ aspectRatio: '16/6', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#8b949e', flexDirection: 'column', gap: 1 }}>
            <CamIcon />
            <Typography variant="caption">دوربین {sideFa(side)} تنظیم نشده — «تنظیمات دوربین» را باز کنید</Typography>
          </Box>
        )}
        <Stack direction="row" spacing={0.5} sx={{ position: 'absolute', top: 8, right: 8 }}>
          <Chip size="small" label={`📹 دوربین ${sideFa(side)}`}
            sx={{ bgcolor: 'rgba(0,0,0,.55)', color: '#fff' }} />
          {live && status?.connected && (
            <Chip size="small" label="زنده" sx={{ bgcolor: 'rgba(46,125,50,.85)', color: '#fff', fontWeight: 700 }} />
          )}
          {live && status?.connected === false && (
            <Chip size="small" label="قطع" color="error" sx={{ fontWeight: 700 }} />
          )}
        </Stack>
        {status?.last_plate && (
          <Chip size="small"
            label={`آخرین پلاک: ${status.last_plate_fa || status.last_plate}`}
            sx={{ position: 'absolute', bottom: 8, right: 8, bgcolor: 'rgba(13,71,161,.85)', color: '#fff', fontWeight: 700 }} />
        )}
      </Box>

      {!!status?.last_error && live && (
        <Alert severity="warning" sx={{ mb: 1 }} icon={false}>
          دوربین: {status.last_error}
        </Alert>
      )}
      {status?.last_ocr_iso && status?.last_plate && (
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
          آخرین خواندن خودکار: {status.last_ocr_iso} — اطمینان {toFa(Math.round((status.last_conf || 0) * 100))}٪
          {status.events_sent ? ` — ${toFa(status.events_sent)} رویداد ثبت‌شده` : ''}
        </Typography>
      )}

      <Stack direction="row" spacing={1} mb={1}>
        <Button size="small" variant="outlined" startIcon={capturing ? <CircularProgress size={16} /> : <CaptureIcon />}
          onClick={capture} disabled={capturing || !live}>
          عکس + خواندن پلاک
        </Button>
        <Button size="small" variant="outlined" startIcon={<WrenchIcon />} onClick={openDialog}>
          تنظیمات دوربین
        </Button>
      </Stack>

      {msg && (
        <Alert severity={msg.kind === 'ok' ? 'success' : 'error'} sx={{ mb: 1 }}
          onClose={() => setMsg(null)}>{msg.text}</Alert>
      )}

      <Dialog open={dialog} onClose={() => setDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          پیکربندی دوربین {sideFa(side)}
        </DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2}>
            <TextField size="small" label={`آدرس RTSP دوربین ${sideFa(side)}`}
              placeholder="rtsp://user:pass@192.168.1.108:554/Streaming/Channels/101"
              value={draft.rtsp} onChange={(e) => setDraft((d) => ({ ...d, rtsp: e.target.value }))}
              fullWidth multiline maxRows={2} />
            <FormControlLabel
              control={<Switch checked={draft.enabled} onChange={(e) => setDraft((d) => ({ ...d, enabled: e.target.checked }))} />}
              label="دوربین فعال باشد (نمایش زنده + خواندن خودکار پلاک)" />
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
              <TextField size="small" type="number" label="فاصلهٔ خواندن خودکار (ثانیه)" sx={{ width: 190 }}
                value={draftGlobal.interval}
                onChange={(e) => setDraftGlobal((g) => ({ ...g, interval: e.target.value }))} />
              <FormControlLabel
                control={<Switch checked={draftGlobal.ocr} onChange={(e) => setDraftGlobal((g) => ({ ...g, ocr: e.target.checked }))} />}
                label="خواندن خودکار پلاک از تصویر (سناریو B)" />
            </Stack>
            <Stack direction="row" spacing={1}>
              <Button variant="contained" startIcon={busy ? <CircularProgress size={16} /> : <WrenchIcon />}
                onClick={testCamera} disabled={busy || !draft.rtsp}>
                تست اتصال
              </Button>
              <Button variant="contained" color="success" onClick={save} disabled={busy}>
                ذخیره
              </Button>
            </Stack>
            {testPreview && (
              <Box sx={{ borderRadius: 2, overflow: 'hidden', border: '1px solid #ccc' }}>
                <img src={`/api/v1/camera/test-frame/${side}?t=${Date.now()}&api_key=${encodeURIComponent(gateKey)}`}
                  alt="پیش‌نمایش تست" style={{ width: '100%', display: 'block' }}
                  onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }} />
              </Box>
            )}
            {msg && <Alert severity={msg.kind === 'ok' ? 'success' : 'error'}>{msg.text}</Alert>}

            <Alert severity="info" variant="outlined">
              <Typography variant="body2" fontWeight={800} mb={0.5}>سناریو A — دوربین پلاک‌خوان (ANPR):</Typography>
              <Typography variant="caption" sx={{ display: 'block', mb: 1 }}>
                اگر دوربین خودش پلاک می‌خواند (Hikvision/Dahua)، در تنظیمات دوربین، آدرس HTTP Event را روی نشانی زیر بگذارید تا رویداد پلاک مستقیم به سرور برسد:
              </Typography>
              <Stack direction="row" spacing={1} alignItems="center">
                <TextField size="small" value={anprUrl} fullWidth
                  InputProps={{ readOnly: true, sx: { fontSize: 11, direction: 'ltr', fontFamily: 'monospace' } }} />
                <IconButton onClick={() => { navigator.clipboard?.writeText(anprUrl); setSnack('نشانی کپی شد ✔') }}>
                  <CopyIcon fontSize="small" />
                </IconButton>
              </Stack>
            </Alert>
            <Alert severity="info" variant="outlined">
              <Typography variant="body2" fontWeight={800} mb={0.5}>سناریو B — دوربین معمولی (RTSP):</Typography>
              <Typography variant="caption" sx={{ display: 'block' }}>
                فقط آدرس RTSP را وارد کنید — سرور هر {toFa(draftGlobal.interval || 10)} ثانیه عکس می‌گیرد، پلاک را با موتور OCR داخلی می‌خواند و رویداد گیت می‌سازد.
              </Typography>
            </Alert>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialog(false)}>بستن</Button>
        </DialogActions>
      </Dialog>

      <Snackbar open={!!snack} autoHideDuration={2000} onClose={() => setSnack('')} message={snack} />
    </Box>
  )
}
