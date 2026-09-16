import { useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, Box, Button, Card, CardContent, Chip, Dialog, DialogActions, DialogContent,
  DialogTitle,
  LinearProgress, MenuItem, Stack, TextField, Typography,
} from '@mui/material'
import { DeleteSweep, Upload } from '@mui/icons-material'
import { api, apiErrorFa } from '../api/client'

export const CAD_STATUS: Record<string, { fa: string; color: string }> = {
  free: { fa: 'آزاد', color: '#21cb83' },
  occupied: { fa: 'اشغال', color: '#f35061' },
  reserved: { fa: 'رزرو', color: '#f6b73c' },
  disabled: { fa: 'غیرفعال', color: '#8193aa' },
  maintenance: { fa: 'تعمیرات', color: '#9b7cf5' },
}

interface Spot {
  id: string; parking_code: string; display_name?: string | null
  polygon_json: { x: number; y: number }[] | null
  center_x?: number | null; center_y?: number | null
  status: string; confidence?: number | null
  source_layer?: string | null; notes?: string | null
}

function parsePoly(raw: unknown): { x: number; y: number }[] {
  if (Array.isArray(raw)) return raw as { x: number; y: number }[]
  if (typeof raw === 'string') { try { return JSON.parse(raw) } catch { return [] } }
  return []
}

/** استخراج آرایه جایگاه‌ها از هر ساختار معقول */
function extractSpots(j: unknown): { spots: Record<string, unknown>[]; source: string } {
  if (Array.isArray(j)) return { spots: j, source: 'آرایه ریشه' }
  if (j && typeof j === 'object') {
    const obj = j as Record<string, unknown>
    if (obj.package_type === 'parking_ai_design_package') {
      throw new Error('این فایل «ورودی» است (پکیج DXF) نه «خروجی مدل» — ابتدا باید آن را به ChatGPT/Claude بدهید و خروجی JSON آن را ذخیره کنید')
    }
    if (Array.isArray(obj.parking_spots)) return { spots: obj.parking_spots as Record<string, unknown>[], source: 'parking_spots' }
    // جستجوی بزرگ‌ترین آرایه شبیه جایگاه
    let best: Record<string, unknown>[] = []
    let bestKey = ''
    for (const [k, v] of Object.entries(obj)) {
      if (Array.isArray(v) && v.length > best.length &&
          v.some((x) => x && typeof x === 'object' && ('polygon' in (x as object) || 'parking_id' in (x as object) || 'parking_code' in (x as object)))) {
        best = v as Record<string, unknown>[]
        bestKey = k
      }
    }
    if (best.length) return { spots: best, source: `کلید «${bestKey}»` }
  }
  throw new Error('در این فایل آرایه‌ای از جایگاه‌های پارکینگ یافت نشد — فایل باید «خروجی JSON مدل» باشد (نه ورودی پکیج)')
}

const CHUNK = 25

export default function CadMap() {
  const qc = useQueryClient()
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const { data: spots } = useQuery({
    queryKey: ['cad-spots'],
    queryFn: async () => (await api.get('/cad-parking')).data as Spot[],
    refetchInterval: 15000,
  })

  const [sel, setSel] = useState<Spot | null>(null)
  const [selStatus, setSelStatus] = useState('free')
  const [selCode, setSelCode] = useState('')

  const importFile = useMutation({
    mutationFn: async (file: File) => {
      const text = await file.text()
      const cleaned = text.replace(/```(json)?/g, '').trim()

      let parsed: unknown
      try {
        parsed = JSON.parse(cleaned)
      } catch {
        // جستجوی شروع JSON (متن توضیحی قبل/بعد)
        const iObj = cleaned.indexOf('{')
        const iArr = cleaned.indexOf('[')
        const start = iArr !== -1 && (iObj === -1 || iArr < iObj) ? iArr : iObj
        if (start === -1) {
          throw new Error('در فایل هیچ JSONی یافت نشد — فایل باید خروجی JSON خالص مدل باشد')
        }
        try {
          parsed = JSON.parse(cleaned.slice(start))
        } catch {
          throw new Error('JSON ناقص است (احتمالاً کپی/ذخیره ناقص شده) — فایل کامل و یکپارچه ذخیره کنید')
        }
      }

      const { spots: all, source } = extractSpots(parsed)
      if (all.length === 0) throw new Error('آرایه جایگاه‌ها خالی است')

      let created = 0, updated = 0, skipped = 0, errCount = 0
      for (let i = 0; i < all.length; i += CHUNK) {
        const chunk = all.slice(i, i + CHUNK)
        try {
          const r = await api.post('/cad-parking/import', { parking_spots: chunk })
          created += r.data.created || 0
          updated += r.data.updated || 0
          skipped += r.data.skipped || 0
          errCount += (r.data.errors || []).length
        } catch (e) {
          const ee = e as { response?: { status?: number; data?: { detail?: string } } }
          if (ee.response) {
            throw new Error(`دسته ${Math.floor(i / CHUNK) + 1}: خطای ${ee.response.status} از سرور`)
          }
          throw new Error(`دسته ${Math.floor(i / CHUNK) + 1}: اتصال به سرور قطع شد — بک‌اند بالا است؟`)
        }
        setProgress({ done: Math.min(i + CHUNK, all.length), total: all.length })
      }
      return { created, updated, skipped, errCount, total: all.length, source }
    },
    onSuccess: (r) => {
      setProgress(null)
      setErr('')
      setMsg(`ورود کامل شد (منبع: ${r.source}): ${r.total} جایگاه — ${r.created} جدید، ${r.updated} به‌روزرسانی، ${r.skipped} رد شده`)
      qc.invalidateQueries({ queryKey: ['cad-spots'] })
    },
    onError: (e) => { setProgress(null); setErr(apiErrorFa(e)) },
  })

  const clearAll = useMutation({
    mutationFn: async () => (await api.delete('/cad-parking/all')).data,
    onSuccess: (r) => { setErr(''); setMsg(`${r.deleted} جایگاه پاک شد`); qc.invalidateQueries({ queryKey: ['cad-spots'] }) },
    onError: (e) => setErr(apiErrorFa(e)),
  })

  const updateSpot = useMutation({
    mutationFn: async () => (await api.patch(`/cad-parking/${sel!.id}`, {
      status: selStatus, parking_code: selCode,
    })).data,
    onSuccess: () => { setSel(null); qc.invalidateQueries({ queryKey: ['cad-spots'] }) },
    onError: (e) => setErr(apiErrorFa(e)),
  })

  const spotsList = spots ?? []

  const geo = useMemo(() => {
    let minX = 1e9, minY = 1e9, maxX = -1e9, maxY = -1e9
    for (const s of spotsList) {
      for (const p of parsePoly(s.polygon_json)) {
        minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x)
        minY = Math.min(minY, p.y); maxY = Math.max(maxY, p.y)
      }
    }
    if (minX > maxX) return null
    const w = maxX - minX || 1, h = maxY - minY || 1
    const pad = 30
    const s = Math.min((900 - pad * 2) / w, (560 - pad * 2) / h)
    return {
      minX, minY,
      tx: (x: number) => pad + (x - minX) * s,
      ty: (y: number) => 560 - pad - (y - minY) * s,
    }
  }, [spotsList])

  const counts = useMemo(() => {
    const c: Record<string, number> = {}
    for (const s of spotsList) c[s.status] = (c[s.status] || 0) + 1
    return c
  }, [spotsList])

  const labelSize = spotsList.length > 60 ? 9 : spotsList.length > 30 ? 11 : 13

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
        <Typography fontWeight={800}>نقشه CAD جایگاه‌ها (از DXF)</Typography>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
          {Object.entries(CAD_STATUS).map(([k, v]) => (
            <Chip key={k} size="small"
              label={`${v.fa}: ${counts[k] || 0}`}
              sx={{ bgcolor: v.color, color: '#fff', fontWeight: 700 }} />
          ))}
          <Button variant="contained" startIcon={<Upload />} component="label" size="small" disabled={!!progress}>
            بارگذاری خروجی AI (JSON)
            <input type="file" accept=".json" hidden
              onChange={(e) => { const f = e.target.files?.[0] ?? null; e.target.value = ''; if (f) importFile.mutate(f) }} ref={fileRef} />
          </Button>
          <Button variant="outlined" color="error" size="small" startIcon={<DeleteSweep />}
            onClick={() => { if (window.confirm('حذف همه جایگاه‌های CAD؟')) clearAll.mutate() }}
            disabled={!!progress || spotsList.length === 0}>
            پاک‌سازی همه
          </Button>
        </Stack>
      </Stack>

      {progress && (
        <Box>
          <LinearProgress variant="determinate"
            value={Math.round((progress.done / progress.total) * 100)} />
          <Typography variant="caption" color="text.secondary">
            در حال ورود: {progress.done} از {progress.total} جایگاه...
          </Typography>
        </Box>
      )}

      {err && <Alert severity="error">{err}</Alert>}
      {msg && <Alert severity="success">{msg}</Alert>}

      <Card>
        <CardContent>
          {spotsList.length === 0 ? (
            <Alert severity="info">
              هنوز جایگاهی وارد نشده — خروجی JSON مدل هوش مصنوعی را با دکمه «بارگذاری خروجی AI» وارد کنید.
            </Alert>
          ) : (
            <Box dir="ltr" sx={{ width: '100%', overflowX: 'auto' }}>
              <svg viewBox="0 0 900 560" style={{ width: '100%', minWidth: 640, display: 'block' }}>
                <rect x="0" y="0" width="900" height="560" fill="#FAFBFC" />
                {geo && spotsList.map((s) => {
                  const poly = parsePoly(s.polygon_json)
                  if (poly.length < 3) return null
                  const col = CAD_STATUS[s.status]?.color ?? '#90A4AE'
                  const cx = s.center_x ?? poly.reduce((a, p) => a + p.x, 0) / poly.length
                  const cy = s.center_y ?? poly.reduce((a, p) => a + p.y, 0) / poly.length
                  return (
                    <g key={s.id} style={{ cursor: 'pointer' }}
                      onClick={() => { setSel(s); setSelStatus(s.status); setSelCode(s.parking_code) }}>
                      <polygon
                        points={poly.map((p) => `${geo.tx(p.x)},${geo.ty(p.y)}`).join(' ')}
                        fill={col} fillOpacity="0.55" stroke={col} strokeWidth="2" />
                      <text x={geo.tx(cx)} y={geo.ty(cy)}
                        textAnchor="middle" fontSize={labelSize} fontWeight="bold" fill="#263238">
                        {s.parking_code}
                      </text>
                    </g>
                  )
                })}
              </svg>
            </Box>
          )}
        </CardContent>
      </Card>

      <Dialog open={sel !== null} onClose={() => setSel(null)}>
        <DialogTitle>جایگاه {sel?.parking_code}</DialogTitle>
        <DialogContent>
          <TextField fullWidth select label="وضعیت" value={selStatus} margin="normal"
            onChange={(e) => setSelStatus(e.target.value)}>
            {Object.entries(CAD_STATUS).map(([k, v]) => (
              <MenuItem key={k} value={k}>
                <Stack direction="row" spacing={1} alignItems="center">
                  <Box sx={{ width: 14, height: 14, borderRadius: '50%', bgcolor: v.color }} />
                  {v.fa}
                </Stack>
              </MenuItem>
            ))}
          </TextField>
          <TextField fullWidth label="شماره جایگاه" value={selCode} margin="normal"
            onChange={(e) => setSelCode(e.target.value)} />
          {sel?.confidence != null && (
            <Typography variant="caption" color="text.secondary">
              اطمینان تشخیص: {(sel.confidence * 100).toFixed(0)}٪ — لایه: {sel.source_layer ?? '—'}
            </Typography>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSel(null)}>انصراف</Button>
          <Button variant="contained" onClick={() => updateSpot.mutate()}>ذخیره</Button>
        </DialogActions>
      </Dialog>
    </Stack>
  )
}