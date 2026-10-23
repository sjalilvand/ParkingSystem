import { useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, Box, Button, Card, CardContent, Chip, Dialog, DialogActions, DialogContent,
  DialogTitle, IconButton, LinearProgress, MenuItem, Stack, TextField, Tooltip, Typography,
} from '@mui/material'
import { CenterFocusStrong, DeleteSweep, Upload, ZoomIn, ZoomOut } from '@mui/icons-material'
import { api, apiErrorFa } from '../api/client'

export const CAD_STATUS: Record<string, { fa: string; color: string }> = {
  free: { fa: 'آزاد', color: '#21cb83' },
  occupied: { fa: 'اشغال', color: '#f35061' },
  reserved: { fa: 'رزرو', color: '#f6b73c' },
  disabled: { fa: 'غیرفعال', color: '#8193aa' },
  maintenance: { fa: 'تعمیرات', color: '#9b7cf5' },
  context: { fa: 'زمینهٔ نقشه', color: '#90A4AE' },
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

/* ---------- هندسهٔ کمکی ---------- */
const CANVAS_W = 1050
const CANVAS_H = 950
const PAD = 36

function centroid(poly: { x: number; y: number }[]) {
  return { x: poly.reduce((a, p) => a + p.x, 0) / poly.length, y: poly.reduce((a, p) => a + p.y, 0) / poly.length }
}

/** کوچک‌سازی چندضلعی به سمت مرکز — برای فاصلهٔ بصری بین جایگاه‌های چسبیده */
function insetPoly(poly: { x: number; y: number }[], f: number) {
  const c = centroid(poly)
  return poly.map((p) => ({ x: c.x + (p.x - c.x) * f, y: c.y + (p.y - c.y) * f }))
}

/** زاویهٔ ضلع بلند چندضلعی (جهت طولانی جایگاه) — نرمال‌شده در [-90,90) */
function longAxisDeg(poly: { x: number; y: number }[]) {
  let best = -1, deg = 0
  for (let i = 0; i < poly.length; i++) {
    for (let j = i + 1; j < poly.length; j++) {
      const dx = poly[j].x - poly[i].x, dy = poly[j].y - poly[i].y
      const d2 = dx * dx + dy * dy
      if (d2 > best) { best = d2; deg = (Math.atan2(dy, dx) * 180) / Math.PI }
    }
  }
  while (deg >= 90) deg -= 180
  while (deg < -90) deg += 180
  return deg
}

/** عرض جاده از notes (قالب «w=6.5») با پیش‌فرض ۵ متر */
function roadWidth(notes: string | null | undefined) {
  const m = /w\s*=\s*([\d.]+)/.exec(notes ?? '')
  return m ? parseFloat(m[1]) : 5
}

interface View { x: number; y: number; w: number; h: number }

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

  // ----- زوم و پن -----
  const [view, setView] = useState<View>({ x: 0, y: 0, w: CANVAS_W, h: CANVAS_H })
  const dragRef = useRef<{ x: number; y: number; vx: number; vy: number; moved: boolean } | null>(null)
  const lastDraggedRef = useRef(false)

  const clampView = (v: View): View => {
    const w = Math.min(v.w, CANVAS_W), h = Math.min(v.h, CANVAS_H)
    return {
      w, h,
      x: Math.min(Math.max(v.x, 0), CANVAS_W - w),
      y: Math.min(Math.max(v.y, 0), CANVAS_H - h),
    }
  }
  const zoom = (f: number) => setView((v) => {
    const nw = Math.min(CANVAS_W, Math.max(CANVAS_W / 6, v.w / f))
    const nh = nw * (CANVAS_H / CANVAS_W)
    const cx = v.x + v.w / 2, cy = v.y + v.h / 2
    return clampView({ x: cx - nw / 2, y: cy - nh / 2, w: nw, h: nh })
  })

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
      setMsg(`ورود کامل شد (منبع: ${r.source}): ${r.total} مورد — ${r.created} جدید، ${r.updated} به‌روزرسانی، ${r.skipped} رد شده`)
      qc.invalidateQueries({ queryKey: ['cad-spots'] })
    },
    onError: (e) => { setProgress(null); setErr(apiErrorFa(e)) },
  })

  const clearAll = useMutation({
    mutationFn: async () => (await api.delete('/cad-parking/all')).data,
    onSuccess: (r) => { setErr(''); setMsg(`${r.deleted} مورد پاک شد`); qc.invalidateQueries({ queryKey: ['cad-spots'] }) },
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
  const contextItems = useMemo(() => spotsList.filter((s) => s.status === 'context'), [spotsList])
  const realSpots = useMemo(() => spotsList.filter((s) => s.status !== 'context'), [spotsList])

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
    const s = Math.min((CANVAS_W - PAD * 2) / w, (CANVAS_H - PAD * 2) / h)
    return {
      minX, minY, s,
      tx: (x: number) => PAD + (x - minX) * s,
      ty: (y: number) => CANVAS_H - PAD - (y - minY) * s,
    }
  }, [spotsList])

  const counts = useMemo(() => {
    const c: Record<string, number> = {}
    for (const s of spotsList) c[s.status] = (c[s.status] || 0) + 1
    return c
  }, [spotsList])

  /* ---------- دسته‌بندی آیتم‌های زمینه ---------- */
  const roads = useMemo(() => contextItems.filter((s) => s.source_layer === 'Road'), [contextItems])
  const rowLabels = useMemo(() => contextItems.filter((s) => s.source_layer === 'RowLabel'), [contextItems])
  const hulls = useMemo(() => contextItems.filter((s) => (s.source_layer ?? '').includes('hull')), [contextItems])
  const buildings = useMemo(() => contextItems.filter(
    (s) => s.source_layer !== 'Road' && s.source_layer !== 'RowLabel' && !(s.source_layer ?? '').includes('hull'),
  ), [contextItems])

  const onPointerDown = (e: ReactPointerEvent<SVGSVGElement>) => {
    dragRef.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y, moved: false }
    try { e.currentTarget.setPointerCapture(e.pointerId) } catch { /* بی‌اهمیت */ }
  }
  const onPointerMove = (e: ReactPointerEvent<SVGSVGElement>) => {
    const d = dragRef.current
    if (!d) return
    const scale = view.w / e.currentTarget.clientWidth
    const dx = (e.clientX - d.x) * scale, dy = (e.clientY - d.y) * scale
    if (Math.abs(e.clientX - d.x) + Math.abs(e.clientY - d.y) > 6) d.moved = true
    setView(clampView({ x: d.vx - dx, y: d.vy - dy, w: view.w, h: view.h }))
  }
  const onPointerUp = () => {
    lastDraggedRef.current = dragRef.current?.moved ?? false
    dragRef.current = null
  }

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
            onClick={() => { if (window.confirm('حذف همهٔ آیتم‌های نقشه CAD؟')) clearAll.mutate() }}
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
            در حال ورود: {progress.done} از {progress.total} مورد...
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
            <Box dir="ltr" sx={{ position: 'relative', width: '100%', overflowX: 'auto' }}>
              {/* دکمه‌های زوم */}
              <Stack spacing={0.5} sx={{ position: 'absolute', top: 10, left: 10, zIndex: 2 }}>
                <Tooltip title="بزرگ‌نمایی">
                  <IconButton size="small" onClick={() => zoom(1.3)}
                    sx={{ bgcolor: '#fff', boxShadow: 1, '&:hover': { bgcolor: '#f0f3f5' } }}>
                    <ZoomIn fontSize="small" />
                  </IconButton>
                </Tooltip>
                <Tooltip title="کوچک‌نمایی">
                  <IconButton size="small" onClick={() => zoom(1 / 1.3)}
                    sx={{ bgcolor: '#fff', boxShadow: 1, '&:hover': { bgcolor: '#f0f3f5' } }}>
                    <ZoomOut fontSize="small" />
                  </IconButton>
                </Tooltip>
                <Tooltip title="نمای کامل">
                  <IconButton size="small" onClick={() => setView({ x: 0, y: 0, w: CANVAS_W, h: CANVAS_H })}
                    sx={{ bgcolor: '#fff', boxShadow: 1, '&:hover': { bgcolor: '#f0f3f5' } }}>
                    <CenterFocusStrong fontSize="small" />
                  </IconButton>
                </Tooltip>
              </Stack>
              <svg viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
                style={{ width: '100%', minWidth: 640, display: 'block', cursor: dragRef.current ? 'grabbing' : 'grab', touchAction: 'none' }}
                onPointerDown={onPointerDown} onPointerMove={onPointerMove}
                onPointerUp={onPointerUp} onPointerLeave={onPointerUp}>
                <rect x="0" y="0" width={CANVAS_W} height={CANVAS_H} fill="#FAFBFC" />

                {/* ۱) محدودهٔ سایت */}
                {geo && hulls.map((s) => {
                  const poly = parsePoly(s.polygon_json)
                  if (poly.length < 3) return null
                  return (
                    <polygon key={s.id} style={{ pointerEvents: 'none' }}
                      points={poly.map((p) => `${geo.tx(p.x)},${geo.ty(p.y)}`).join(' ')}
                      fill="#EDF2EE" stroke="#9FB4A6" strokeWidth="2.2" strokeLinejoin="round" />
                  )
                })}

                {/* ۲) جاده‌ها — پلی‌لاین با پهنای واقعی از DXF */}
                {geo && roads.map((r) => {
                  const pts = parsePoly(r.polygon_json)
                  if (pts.length < 2) return null
                  const wPx = roadWidth(r.notes) * geo.s
                  const d = pts.map((p, i) => `${i === 0 ? 'M' : 'L'} ${geo.tx(p.x)} ${geo.ty(p.y)}`).join(' ')
                  return (
                    <g key={r.id} style={{ pointerEvents: 'none' }}>
                      <path d={d} fill="none" stroke="#C2CDD5" strokeWidth={wPx + 1.4} strokeLinecap="round" strokeLinejoin="round" />
                      <path d={d} fill="none" stroke="#D8E0E5" strokeWidth={wPx} strokeLinecap="round" strokeLinejoin="round" />
                      <path d={d} fill="none" stroke="#FFFFFF" strokeWidth={Math.max(0.9, geo.s * 0.22)}
                        strokeDasharray={`${geo.s * 2.4} ${geo.s * 2}`} strokeLinecap="round" />
                    </g>
                  )
                })}

                {/* ۳) ساختمان‌ها — توپر و خوانا */}
                {geo && buildings.map((s) => {
                  const poly = parsePoly(s.polygon_json)
                  if (poly.length < 3) return null
                  const c = s.center_x != null && s.center_y != null
                    ? { x: s.center_x, y: s.center_y } : centroid(poly)
                  const name = (s.display_name ?? '').split('(')[0].trim()
                  return (
                    <g key={s.id} style={{ pointerEvents: 'none' }}>
                      <polygon
                        points={poly.map((p) => `${geo.tx(p.x)},${geo.ty(p.y)}`).join(' ')}
                        fill="#D8E0E8" stroke="#8FA1B3" strokeWidth="1.6" strokeLinejoin="round" />
                      {name && (
                        <text x={geo.tx(c.x)} y={geo.ty(c.y)} textAnchor="middle" dominantBaseline="central"
                          fontSize="15" fontWeight="800" fill="#546E7A" style={{ userSelect: 'none' }}>
                          {name}
                        </text>
                      )}
                    </g>
                  )
                })}

                {/* ۴) جایگاه‌ها — با فاصلهٔ بصری (inset) و برچسب چرخیده خوانا */}
                {geo && realSpots.map((s) => {
                  const poly = parsePoly(s.polygon_json)
                  if (poly.length < 3) return null
                  const col = CAD_STATUS[s.status]?.color ?? '#90A4AE'
                  const c = s.center_x != null && s.center_y != null
                    ? { x: s.center_x, y: s.center_y } : centroid(poly)
                  const cx = geo.tx(c.x), cy = geo.ty(c.y)
                  const deg = longAxisDeg(poly)
                  const longPx = Math.max(...poly.map((p, i) => {
                    const q = poly[(i + 1) % poly.length]
                    return Math.hypot(q.x - p.x, q.y - p.y)
                  })) * geo.s
                  const font = Math.min(12.5, Math.max(8.5, longPx * 0.28))
                  const inner = insetPoly(poly, 0.86)
                  return (
                    <g key={s.id} className="cad-spot" style={{ cursor: 'pointer' }}
                      onClick={() => { if (lastDraggedRef.current) return; setSel(s); setSelStatus(s.status); setSelCode(s.parking_code) }}>
                      <polygon
                        points={inner.map((p) => `${geo.tx(p.x)},${geo.ty(p.y)}`).join(' ')}
                        fill={col} fillOpacity="0.92" stroke="#FFFFFF" strokeWidth="0.8" strokeLinejoin="round" />
                      <text x={cx} y={cy} transform={`rotate(${deg} ${cx} ${cy})`}
                        textAnchor="middle" dominantBaseline="central"
                        fontSize={font} fontWeight="700" fill="#132430"
                        stroke="#FFFFFF" strokeWidth="2.6" paintOrder="stroke"
                        style={{ userSelect: 'none' }}>
                        {s.parking_code}
                      </text>
                    </g>
                  )
                })}

                {/* ۵) برچسب ردیف‌ها */}
                {geo && rowLabels.map((s) => {
                  if (s.center_x == null || s.center_y == null) return null
                  const cx = geo.tx(s.center_x), cy = geo.ty(s.center_y)
                  const name = s.display_name ?? s.parking_code
                  const tw = name.length * 7.4 + 16
                  return (
                    <g key={s.id} style={{ pointerEvents: 'none' }}>
                      <rect x={cx - tw / 2} y={cy - 10.5} width={tw} height={21} rx={7}
                        fill="#37474F" fillOpacity="0.93" />
                      <text x={cx} y={cy} textAnchor="middle" dominantBaseline="central"
                        fontSize="12.5" fontWeight="800" fill="#FFFFFF" style={{ userSelect: 'none' }}>
                        {name}
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
            {Object.entries(CAD_STATUS).filter(([k]) => k !== 'context').map(([k, v]) => (
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
