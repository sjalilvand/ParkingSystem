import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, Box, Button, Card, CardContent, Chip, Dialog, DialogActions,
  DialogContent, DialogTitle, MenuItem, Stack, TextField, Typography,
} from '@mui/material'
import { Delete, Print, Save, Upload } from '@mui/icons-material'
import { api, apiErrorFa } from '../api/client'

interface Space {
  id: string; code: string; floor: number; zone: string | null
  parking_type: string; status: string; is_active: boolean
  map_x: number | null; map_y: number | null
}
interface Pt { x: number; y: number }

export default function MapDesigner() {
  const qc = useQueryClient()
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [points, setPoints] = useState<Record<string, Pt>>({})
  const [dirty, setDirty] = useState(false)
  const [pending, setPending] = useState<Pt | null>(null)
  const [assignSel, setAssignSel] = useState('')

  const { data: mapSet } = useQuery({
    queryKey: ['set', 'parking_map'],
    queryFn: async () => (await api.get('/app-settings/parking_map')).data as { value: { data_url?: string } | null },
  })
  const dataUrl = mapSet?.value?.data_url
  const { data: spaces } = useQuery({
    queryKey: ['ps-all'],
    queryFn: async () => (await api.get('/parking-spaces')).data as Space[],
  })

  useEffect(() => {
    if (!spaces) return
    const p: Record<string, Pt> = {}
    for (const s of spaces) if (s.map_x != null && s.map_y != null) p[s.id] = { x: s.map_x, y: s.map_y }
    setPoints(p); setDirty(false)
  }, [spaces])

  const saveImage = useMutation({
    mutationFn: async (data_url: string) =>
      (await api.put('/app-settings/parking_map', { value: { data_url }, reason: 'map-designer' })).data,
    onSuccess: () => { setErr(''); setMsg('تصویر نقشه ذخیره شد'); qc.invalidateQueries({ queryKey: ['set'] }) },
    onError: (e) => setErr(apiErrorFa(e)),
  })
  const savePoints = useMutation({
    mutationFn: async () => (await api.post('/parking/map-coordinates', {
      points: Object.entries(points).map(([space_id, v]) => ({ space_id, x: v.x, y: v.y })),
    })).data,
    onSuccess: () => { setErr(''); setMsg('نقاط ذخیره شد'); setDirty(false); qc.invalidateQueries({ queryKey: ['ps-all'] }) },
    onError: (e) => setErr(apiErrorFa(e)),
  })

  const onFile = (f: File | null) => {
    if (!f) return
    if (f.size > 3 * 1024 * 1024) { setErr('حجم تصویر باید کمتر از ۳ مگابایت باشد'); return }
    const rd = new FileReader()
    rd.onload = () => saveImage.mutate(String(rd.result))
    rd.readAsDataURL(f)
  }

  const onClickImage = (e: React.MouseEvent<HTMLImageElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    if (!rect.width || !rect.height) return
    setPending({
      x: Math.round(((e.clientX - rect.left) / rect.width) * 10000),
      y: Math.round(((e.clientY - rect.top) / rect.height) * 10000),
    })
    setAssignSel('')
  }

  const spaceById = (id: string) => (spaces ?? []).find((s) => s.id === id)
  const assigned = Object.entries(points)

  return (
    <Stack spacing={2}>
      {err && <Alert severity="error">{err}</Alert>}
      {msg && <Alert severity="success">{msg}</Alert>}

      <Card><CardContent>
        <Typography fontWeight={800} mb={1}>طراح نقشه پارکینگ (کلیک روی تصویر = ثبت نقطه)</Typography>
        <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap alignItems="center" mb={1.5}>
          <Button variant="contained" component="label" startIcon={<Upload />}>
            بارگذاری تصویر نقشه
            <input type="file" accept="image/*" hidden
              onChange={(e) => onFile(e.target.files?.[0] ?? null)} />
          </Button>
          <Button variant="contained" startIcon={<Save />} disabled={!dirty || savePoints.isPending}
            onClick={() => savePoints.mutate()}>
            ذخیره نقاط ({assigned.length})
          </Button>
          <Button variant="outlined" startIcon={<Print />} onClick={() => window.print()}>
            چاپ برگه راهنما
          </Button>
          {(spaces ?? []).length > 0 && (
            <Chip size="small" variant="outlined"
              label={`مسقف آزاد: ${(spaces ?? []).filter((s) => s.status === 'FREE' && s.is_active).length} / اشغال: ${(spaces ?? []).filter((s) => s.status === 'OCCUPIED').length}`} />
          )}
        </Stack>
        <Typography variant="caption" color="text.secondary">
          رنگ هر نقطه از وضعیت واقعی جایگاه می‌آید (سبز آزاد، قرمز اشغال) — نه رنگ دستی.
          برای حذف/جابه‌جایی نقطه، روی آن کلیک کنید.
        </Typography>
      </CardContent></Card>

      <Box className="map-print" sx={{ border: '1px solid #E3EAF2', borderRadius: 2, p: 1, bgcolor: '#fff' }}>
        {dataUrl ? (
          <Box sx={{ position: 'relative' }}>
            <img src={dataUrl} alt="نقشه پارکینگ" onClick={onClickImage}
              style={{ width: '100%', display: 'block', cursor: 'crosshair', borderRadius: 6 }} />
            {assigned.map(([id, pt]) => {
              const sp = spaceById(id)
              return (
                <Box key={id}
                  onClick={() => { setPending({ x: pt.x, y: pt.y }); setAssignSel(id) }}
                  sx={{ position: 'absolute', left: `${pt.x / 100}%`, top: `${pt.y / 100}%`,
                    transform: 'translate(-50%, -50%)',
                    bgcolor: sp?.status === 'OCCUPIED' ? '#C62828' : '#2E7D32',
                    color: '#fff', borderRadius: 999, px: 0.9, py: 0.2,
                    fontSize: 11, fontWeight: 800, border: '2px solid #fff',
                    boxShadow: 2, cursor: 'pointer', whiteSpace: 'nowrap' }}>
                  {sp?.code ?? '?'}
                </Box>
              )
            })}
          </Box>
        ) : (
          <Alert severity="info">هنوز تصویری بارگذاری نشده است — با دکمهٔ «بارگذاری تصویر نقشه» شروع کنید.</Alert>
        )}
      </Box>

      <Dialog open={!!pending} onClose={() => setPending(null)}>
        <DialogTitle>اتصال نقطه به جایگاه</DialogTitle>
        <DialogContent>
          <Typography variant="caption" color="text.secondary">
            مختصات: {(pending?.x ?? 0) / 100}% — {(pending?.y ?? 0) / 100}%
          </Typography>
          <TextField select size="small" label="جایگاه" value={assignSel} fullWidth sx={{ mt: 1 }}
            onChange={(e) => setAssignSel(e.target.value)}>
            {(spaces ?? []).map((s) => (
              <MenuItem key={s.id} value={s.id}>
                {s.code}{s.zone ? ` (${s.zone})` : ''}{s.status === 'OCCUPIED' ? ' — اشغال' : ''}
              </MenuItem>
            ))}
          </TextField>
        </DialogContent>
        <DialogActions>
          {assignSel && points[assignSel] && (
            <Button color="error" startIcon={<Delete />}
              onClick={() => {
                setPoints((p) => { const q = { ...p }; delete q[assignSel]; return q })
                setDirty(true); setPending(null)
              }}>
              حذف نقطه
            </Button>
          )}
          <Button onClick={() => setPending(null)}>انصراف</Button>
          <Button variant="contained" disabled={!assignSel}
            onClick={() => {
              if (pending) setPoints((p) => ({ ...p, [assignSel]: pending }))
              setDirty(true); setPending(null)
            }}>
            اتصال
          </Button>
        </DialogActions>
      </Dialog>

      <style>{'@media print { body * { visibility: hidden !important } .map-print, .map-print * { visibility: visible !important } .map-print { position: fixed; top: 0; right: 0; width: 100%; } }'}</style>
    </Stack>
  )
}
