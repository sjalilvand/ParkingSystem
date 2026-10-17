import { useCallback, useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Alert, Box, Button, Card, CardContent, Chip, Divider,
  FormControlLabel, LinearProgress, Slider, Stack, Switch, Typography,
} from '@mui/material'
import {
  CameraAlt, Image as ImageIcon, Refresh, RestartAlt, Visibility,
} from '@mui/icons-material'
import { api, apiErrorFa } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import PlateBox from '../components/PlateBox'

interface OcrPlate {
  raw?: string | null
  persian?: string | null
  system?: string | null
  valid?: boolean
  confidence?: number
  method?: string | null
  color?: string | null
  color_score?: number
  box?: number[] | null
  crop_b64?: string | null
}
interface VehicleHit {
  vehicle_id: string
  plate_normalized?: string
  plate_raw?: string
  plate_type?: string
  vehicle_type?: string
  brand?: string | null
  model?: string | null
  color?: string | null
}
interface OcrResult {
  success: boolean
  best: OcrPlate | null
  plates: OcrPlate[]
  vehicles: VehicleHit[]
  engine: { detector?: string; ocr?: string; easyocr_error?: string | null }
  elapsed_ms: number
  annotated_b64?: string | null
}
interface OcrStatus {
  ready: boolean
  models_dir: string
  capabilities: Record<string, boolean>
  install_hint: string | null
}

const pct = (c?: number) => (typeof c === 'number' ? `${Math.round(c <= 1 ? c * 100 : c)}٪` : '-')

export default function PlateOcr() {
  const { can } = useAuth()
  const canLookup = can('vehicles.view') || can('gate.manual_access')
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [lookup, setLookup] = useState(true)
  const [minConf, setMinConf] = useState(0.25)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [res, setRes] = useState<OcrResult | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const { data: st, refetch: refetchStatus } = useQuery({
    queryKey: ['plate-ocr-status'],
    queryFn: async () => (await api.get('/plate-ocr/status')).data as OcrStatus,
  })

  const pick = useCallback((f: File | null | undefined) => {
    if (!f) return
    setFile(f)
    setRes(null)
    setErr('')
    const rd = new FileReader()
    rd.onload = () => setPreview(String(rd.result))
    rd.readAsDataURL(f)
  }, [])

  // Ctrl+V برای چسباندن تصویر از کلیپ‌بورد
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const item = Array.from(e.clipboardData?.items ?? []).find((i) => i.type.startsWith('image/'))
      if (item) pick(item.getAsFile())
    }
    window.addEventListener('paste', onPaste)
    return () => window.removeEventListener('paste', onPaste)
  }, [pick])

  const analyze = async () => {
    if (!file) { setErr('ابتدا تصویر خودرو را انتخاب کن (فایل / کشیدن‌ورها / Ctrl+V).'); return }
    setBusy(true); setErr(''); setRes(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const r = await api.post('/plate-ocr/read', fd, {
        params: { lookup: lookup && canLookup, min_conf: minConf },
        timeout: 120000,
      })
      setRes(r.data as OcrResult)
    } catch (e) { setErr(apiErrorFa(e)) } finally { setBusy(false) }
  }

  const reset = () => { setFile(null); setPreview(null); setRes(null); setErr('') }

  const best = res?.best
  const engineFa = (e?: { detector?: string; ocr?: string }) => {
    if (!e) return ''
    const det = e.detector === 'yolo' ? 'YOLO' : 'تشخیص کلاسیک (CV)'
    const ocr = e.ocr === 'crnn+easyocr' ? 'CRNN + EasyOCR' : 'EasyOCR'
    return `${det} + ${ocr}`
  }

  return (
    <Stack spacing={2}>
      <Typography variant="h6" fontWeight={800}>📷 پلاک‌خوان (OCR) — آپلود عکس خودرو و تشخیص پلاک</Typography>

      {/* وضعیت موتور */}
      {st && (
        <Alert severity={st.ready ? 'success' : 'warning'} icon={<CameraAlt />}>
          {st.ready ? 'موتور پلاک‌خوان آماده است ✓' : 'موتور OCR نصب نشده — می‌توانی ادامه بدهی اما خطای وابستگی می‌بینی.'}
          {st.ready ? ' ' : ' '}
          <Box component="code" sx={{ fontSize: 11 }}>
            {`تشخیص: ${st.capabilities?.yolo_weights && st.capabilities?.ultralytics ? 'YOLO ✓' : 'کلاسیک'} | OCR: ${st.capabilities?.easyocr ? 'EasyOCR ✓' : ''}${st.capabilities?.crnn_weights && st.capabilities?.torch ? ' CRNN ✓' : ''}`}
          </Box>
          {!st.ready && st.install_hint && (
            <Typography variant="caption" component="div" sx={{ mt: 0.5 }}>
              نصب: <Box component="code">{st.install_hint}</Box> (بار اول مدل‌های EasyOCR دانلود می‌شود)
            </Typography>
          )}
        </Alert>
      )}
      {err && <Alert severity="error" onClose={() => setErr('')}>{err}</Alert>}

      {/* آپلود */}
      <Card><CardContent>
        <Stack direction="row" spacing={1.2} alignItems="center" flexWrap="wrap" useFlexGap>
          <ImageIcon color="primary" />
          <Typography fontWeight={800} sx={{ flex: 1 }}>تصویر خودرو (jpg / png / webp / bmp)</Typography>
          <Button size="small" startIcon={<Refresh />} onClick={() => refetchStatus()}>بررسی وضعیت موتور</Button>
        </Stack>
        <Box
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => { e.preventDefault(); setDragOver(false); pick(e.dataTransfer.files?.[0]) }}
          sx={{
            mt: 1.5, p: 3, textAlign: 'center', cursor: 'pointer', borderRadius: 2.5,
            border: '2px dashed', borderColor: dragOver ? 'primary.main' : '#B0C4D8',
            bgcolor: dragOver ? 'rgba(21,101,192,0.06)' : 'rgba(240,244,248,0.6)',
            transition: 'all .2s',
          }}
        >
          <input
            ref={inputRef} type="file" hidden accept="image/jpeg,image/png,image/webp,image/bmp"
            onChange={(e) => pick(e.target.files?.[0])}
          />
          {preview
            ? <Box component="img" src={preview} alt="پیش‌نمایش" sx={{ maxHeight: 260, maxWidth: '100%', borderRadius: 2 }} />
            : (
              <Stack spacing={1} alignItems="center">
                <CameraAlt sx={{ fontSize: 46, color: '#78909C' }} />
                <Typography fontWeight={800}>فایل را اینجا بکش و رها کن — یا کلیک کن</Typography>
                <Typography variant="caption" color="text.secondary">
                  می‌توانی از کلیپ‌بورد هم بچسبانی: <b>Ctrl+V</b>
                </Typography>
              </Stack>
            )}
        </Box>

        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} alignItems={{ sm: 'center' }} mt={1.5} flexWrap="wrap" useFlexGap>
          <Button variant="contained" startIcon={<CameraAlt />} disabled={busy || !file} onClick={analyze}>
            تشخیص پلاک
          </Button>
          <Button variant="text" startIcon={<RestartAlt />} disabled={busy} onClick={reset}>پاک کردن</Button>
          <Box sx={{ minWidth: 220, flex: 1, maxWidth: 340 }}>
            <Typography variant="caption" color="text.secondary">
              حداقل اطمینان: <b>{Math.round(minConf * 100)}٪</b>
            </Typography>
            <Slider size="small" min={0.05} max={0.95} step={0.05} value={minConf}
              onChange={(_, v) => setMinConf(v as number)} valueLabelDisplay="auto"
              valueLabelFormat={(v) => `${Math.round(v * 100)}٪`} />
          </Box>
          <FormControlLabel
            control={<Switch checked={lookup && canLookup} disabled={!canLookup}
              onChange={(e) => setLookup(e.target.checked)} size="small" />}
            label="جستجو در خودروهای ثبت‌شده"
          />
          {!canLookup && (
            <Typography variant="caption" color="text.secondary">
              (جستجوی خودرو نیاز به مجوز vehicles.view دارد)
            </Typography>
          )}
        </Stack>
        {busy && <LinearProgress sx={{ mt: 1.5 }} />}
      </CardContent></Card>

      {/* نتیجه */}
      {res && (
        <Card><CardContent>
          <Stack direction="row" spacing={1.2} alignItems="center" flexWrap="wrap" useFlexGap>
            <Visibility color="primary" />
            <Typography fontWeight={800} sx={{ flex: 1 }}>نتیجهٔ تشخیص</Typography>
            <Chip size="small" variant="outlined" label={`⏱ ${res.elapsed_ms ?? 0} میلی‌ثانیه`} />
            {res.engine && <Chip size="small" color="info" variant="outlined" label={engineFa(res.engine)} />}
            <Chip size="small" color={res.success ? 'success' : 'warning'}
              label={res.success ? 'پلاک یافت شد ✓' : 'پلاکی یافت نشد'} />
          </Stack>

          {best ? (
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} mt={1.5} alignItems={{ md: 'flex-start' }}>
              <Stack spacing={1} sx={{ minWidth: 260 }}>
                <Typography variant="caption" color="text.secondary">بهترین کاندیدا:</Typography>
                <PlateBox plate={best.persian || best.raw} size="lg" />
                <Stack direction="row" spacing={0.8} flexWrap="wrap" useFlexGap>
                  <Chip size="small" color={best.valid ? 'success' : 'error'}
                    label={best.valid ? 'قالب معتبر ✓' : 'قالب نامعتبر ✗'} />
                  <Chip size="small" variant="outlined" label={`اطمینان: ${pct(best.confidence)}`} />
                  {best.color && <Chip size="small" variant="outlined" label={`رنگ: ${best.color}`} />}
                  {best.method && <Chip size="small" variant="outlined" sx={{ fontSize: 11 }} label={`روش: ${best.method}`} />}
                </Stack>
                {best.system && (
                  <Typography variant="body2" component="div">
                    قالب سیستمی: <Box component="code" sx={{ direction: 'ltr', display: 'inline-block' }}>{best.system}</Box>
                  </Typography>
                )}
              </Stack>
              {res.annotated_b64 && (
                <Box sx={{ flex: 1, textAlign: 'center' }}>
                  <Typography variant="caption" color="text.secondary">تصویر تحلیل‌شده (کادر پلاک):</Typography>
                  <Box component="img"
                    src={`data:image/jpeg;base64,${res.annotated_b64}`}
                    alt="annotated" sx={{ maxHeight: 300, maxWidth: '100%', borderRadius: 2, border: '1px solid #E3EAF2' }} />
                </Box>
              )}
            </Stack>
          ) : (
            <Typography color="text.secondary" mt={1.5}>
              پلاکی با حداقل اطمینانِ انتخابی خوانده نشد — حداقل اطمینان را کمتر کن یا از عکس واضح‌تر استفاده کن.
            </Typography>
          )}

          {/* جستجوی خودرو */}
          {(res.vehicles?.length ?? 0) > 0 && (
            <Box mt={2}>
              <Typography fontWeight={800} mb={1}>خودروهای مطابق در سامانه:</Typography>
              <Stack spacing={1}>
                {res.vehicles.map((v) => (
                  <Stack key={v.vehicle_id} direction={{ xs: 'column', sm: 'row' }} spacing={1.2}
                    alignItems={{ sm: 'center' }} sx={{ border: '1px solid #E3EAF2', borderRadius: 2.5, p: 1.2 }}>
                    <PlateBox plate={v.plate_raw} size="sm" />
                    <Chip size="small" variant="outlined" label={v.brand || '—'} />
                    {v.color && <Chip size="small" variant="outlined" label={v.color} />}
                    {v.plate_type && <Chip size="small" variant="outlined" label={v.plate_type} />}
                  </Stack>
                ))}
              </Stack>
            </Box>
          )}

          <Divider sx={{ my: 2 }} />
          {/* همهٔ کاندیداها */}
          <Typography fontWeight={800} mb={1}>همهٔ کاندیداها ({res.plates?.length ?? 0}):</Typography>
          <Stack spacing={1}>
            {(res.plates ?? []).map((p, i) => (
              <Stack key={i} direction={{ xs: 'column', sm: 'row' }} spacing={1.2} alignItems={{ sm: 'center' }}
                sx={{ border: '1px solid #E3EAF2', borderRadius: 2.5, p: 1 }} flexWrap="wrap" useFlexGap>
                {p.crop_b64 && (
                  <Box component="img" src={`data:image/jpeg;base64,${p.crop_b64}`}
                    alt={`crop-${i}`} sx={{ height: 40, borderRadius: 1, border: '1px solid #CFD8DC' }} />
                )}
                <PlateBox plate={p.persian || p.raw} size="sm" />
                <Chip size="small" color={p.valid ? 'success' : 'error'} variant="outlined"
                  label={p.valid ? 'معتبر' : 'نامعتبر'} />
                <Chip size="small" variant="outlined" label={`اطمینان: ${pct(p.confidence)}`} />
                {p.color && <Chip size="small" variant="outlined" label={p.color} />}
                {p.method && <Typography variant="caption" color="text.secondary">{p.method}</Typography>}
                {p.system && (
                  <Typography variant="caption" sx={{ direction: 'ltr', fontFamily: 'monospace' }}>{p.system}</Typography>
                )}
              </Stack>
            ))}
          </Stack>
          {res.engine?.easyocr_error && (
            <Alert severity="warning" sx={{ mt: 2 }}>
              خطای EasyOCR: <Box component="code" sx={{ fontSize: 11 }}>{String(res.engine.easyocr_error)}</Box>
            </Alert>
          )}
        </CardContent></Card>
      )}

      <Typography variant="caption" color="text.secondary">
        نکته: همین سرویس پشت‌صحنهٔ گیت هم است — دکمهٔ «تشخیص پلاک» همان endpoint صفحهٔ تست قدیمی
        (/plate-ocr/read) را صدا می‌زند؛ بار اول که EasyOCR اجرا شود، دانلود مدل ممکن است کمی طول بکشد.
      </Typography>
    </Stack>
  )
}
