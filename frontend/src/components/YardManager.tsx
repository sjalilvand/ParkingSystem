import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, Box, Button, Card, CardContent, Chip, InputAdornment, Stack,
  TextField, ToggleButton, ToggleButtonGroup, Tooltip, Typography,
} from '@mui/material'
import { Add, DirectionsCar, GridOn, LocalParking, Search } from '@mui/icons-material'
import { api, apiErrorFa } from '../api/client'

interface Space {
  id: string; code: string; zone: string | null; parking_type: string
  status: string; is_active: boolean
}
interface Cap {
  declared_capacity: number | null; capacity_source: string
  registered_yard_count: number; confirmed_presence: number
  available: number | null; accepting: boolean
}

const STATUS_META: Record<string, { fa: string; bg: string; border: string; text: string }> = {
  FREE: { fa: 'آزاد', bg: 'linear-gradient(160deg,#E8F5E9,#C8E6C9)', border: '#66BB6A', text: '#1B5E20' },
  OCCUPIED: { fa: 'اشغال', bg: 'linear-gradient(160deg,#FFEBEE,#FFCDD2)', border: '#EF5350', text: '#B71C1C' },
}
const meta = (st: string) => STATUS_META[st] ?? { fa: st, bg: '#ECEFF1', border: '#90A4AE', text: '#37474F' }

export default function YardManager() {
  const qc = useQueryClient()
  const [err, setErr] = useState(''); const [msg, setMsg] = useState('')
  const [prefix, setPrefix] = useState('Y')
  const [count, setCount] = useState(10)
  const [capDraft, setCapDraft] = useState<number | null>(null)
  const [q, setQ] = useState('')
  const [filter, setFilter] = useState<'ALL' | 'FREE' | 'OCCUPIED'>('ALL')

  const { data: spaces } = useQuery({
    queryKey: ['ps-all'], queryFn: async () => (await api.get('/parking-spaces')).data as Space[],
  })
  const { data: cap } = useQuery({
    queryKey: ['cap-status'], queryFn: async () => (await api.get('/parking/capacity-status')).data as Cap,
  })
  const yard = useMemo(() => (spaces ?? []).filter((s) => s.parking_type === 'YARD'), [spaces])

  const groups = useMemo(() => {
    const g: Record<string, Space[]> = {}
    for (const s of yard) {
      const pre = s.code.includes('-') ? s.code.split('-')[0] : s.code
      ;(g[pre] ??= []).push(s)
    }
    return Object.entries(g).sort((a, b) => b[1].length - a[1].length)
  }, [yard])

  const visible = useMemo(() => yard.filter((s) =>
    (filter === 'ALL' || s.status === filter) &&
    (!q.trim() || s.code.toLowerCase().includes(q.trim().toLowerCase()))
  ), [yard, q, filter])

  const free = yard.filter((s) => s.status === 'FREE').length
  const occ = yard.filter((s) => s.status === 'OCCUPIED').length

  const invalidate = () => qc.invalidateQueries({ queryKey: ['ps-all', 'cap-status'] })

  const bulk = useMutation({
    mutationFn: async () => (await api.post('/parking/yard-spaces', { count, prefix })).data as
      { created: string[]; skipped_existing: string[] },
    onSuccess: (d) => {
      setErr('')
      setMsg(d.created.length > 0
        ? `✅ ${d.created.length} جایگاه جدید ساخته شد — از ${d.created[0]} تا ${d.created[d.created.length - 1]}`
        : `همهٔ شماره‌های ${prefix}-0001 تا ... از قبل موجود بودند (چیزی ساخته نشد)`)
      invalidate()
    },
    onError: (e) => setErr(apiErrorFa(e)),
  })
  const del = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/parking/yard-spaces/${id}`)).data,
    onSuccess: () => { setErr(''); setMsg('جایگاه حذف شد'); invalidate() },
    onError: (e) => setErr(apiErrorFa(e)),
  })
  const saveCap = useMutation({
    mutationFn: async (total: number) =>
      (await api.put('/app-settings/yard_capacity', { value: { total }, reason: 'yard-manager' })).data,
    onSuccess: () => { setErr(''); setMsg('ظرفیت ذخیره شد — بلافاصله در موتور ورود اعمال می‌شود'); invalidate() },
    onError: (e) => setErr(apiErrorFa(e)),
  })

  const preview = useMemo(() => {
    const n = Math.min(count, 500)
    return Array.from({ length: n }, (_, i) => `${prefix.trim() || 'Y'}-${String(i + 1).padStart(4, '0')}`)
  }, [prefix, count])

  return (
    <Stack spacing={2}>
      {err && <Alert severity="error">{err}</Alert>}
      {msg && <Alert severity="success" variant="filled">{msg}</Alert>}

      {/* ===== ثبت ===== */}
      <Card sx={{ borderRadius: 3, overflow: 'hidden' }}>
        <Box sx={{ background: 'linear-gradient(135deg,#1565C0,#1E88E5)', color: '#fff', px: 2.5, py: 1.5,
                   display: 'flex', alignItems: 'center', gap: 1 }}>
          <LocalParking />
          <Typography fontWeight={900} fontSize={16}>ثبت جایگاه‌های محوطه</Typography>
        </Box>
        <CardContent sx={{ pt: 2 }}>
          <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap alignItems="center">
            <TextField size="small" label="پیش‌وند" value={prefix} sx={{ width: 110 }}
              onChange={(e) => setPrefix(e.target.value.replace(/[^A-Za-z0-9\u0600-\u06FF]/g, ''))}
              InputProps={{ startAdornment: <InputAdornment position="start">#</InputAdornment> }} />
            <TextField size="small" type="number" label="تعداد" value={String(count)} sx={{ width: 110 }}
              onChange={(e) => setCount(Math.max(1, Math.min(500, Number(e.target.value) || 1)))} />
            <Button variant="contained" size="large" startIcon={<Add />}
              disabled={bulk.isPending || count < 1} onClick={() => bulk.mutate()}
              sx={{ borderRadius: 2, px: 3 }}>
              ثبت {count} جایگاه
            </Button>
          </Stack>
          <Box mt={1.5} sx={{ bgcolor: '#F0F4F8', borderRadius: 2, p: 1.2, px: 2 }}>
            <Typography variant="body2">
              <Typography component="span" fontWeight={800}>پیش‌نمایش شماره‌گذاری: </Typography>
              {preview.slice(0, 4).map((c) => (
                <Chip key={c} size="small" label={c} sx={{ mx: 0.3, fontFamily: 'monospace', direction: 'ltr' }} />
              ))}
              {preview.length > 4 && <Typography component="span" color="text.secondary"> … تا {preview[preview.length - 1]}</Typography>}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              اجرای دوباره بی‌خطر است — شماره‌های موجود دوباره ساخته نمی‌شوند و فقط کمبودها تکمیل می‌شوند.
            </Typography>
          </Box>
        </CardContent>
      </Card>

      {/* ===== ظرفیت ===== */}
      <Card sx={{ borderRadius: 3, overflow: 'hidden' }}>
        <Box sx={{ background: 'linear-gradient(135deg,#2E7D32,#43A047)', color: '#fff', px: 2.5, py: 1.5,
                   display: 'flex', alignItems: 'center', gap: 1 }}>
          <GridOn />
          <Typography fontWeight={900} fontSize={16}>ظرفیت اعلامی محوطه</Typography>
        </Box>
        <CardContent sx={{ pt: 2 }}>
          <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap alignItems="center">
            <TextField size="small" type="number" label="ظرفیت (خودرو)" sx={{ width: 150 }}
              value={String(capDraft ?? cap?.declared_capacity ?? '')}
              onChange={(e) => setCapDraft(Number(e.target.value) || 0)} />
            <Button variant="contained" color="success" disabled={saveCap.isPending}
              onClick={() => saveCap.mutate(Number(capDraft ?? cap?.declared_capacity ?? 0))}>
              ذخیره ظرفیت
            </Button>
            {cap && (
              <>
                <Chip label={`ثبت‌شده در سیستم: ${cap.registered_yard_count}`} variant="outlined" />
                <Chip label={`حضور فعلی: ${cap.confirmed_presence}`} variant="outlined" />
                <Chip color={cap.accepting ? 'success' : 'error'}
                  label={cap.accepting ? '🟢 پذیرش باز' : '🔴 ظرفیت پر — مرجوع به اپراتور'} />
                <Chip size="small" variant="outlined"
                  label={`منبع: ${cap.capacity_source === 'setting' ? 'طراح' : cap.capacity_source === 'env' ? 'env' : 'نامحدود'}`} />
              </>
            )}
          </Stack>
        </CardContent>
      </Card>

      {/* ===== جایگاه‌ها ===== */}
      <Card sx={{ borderRadius: 3, overflow: 'hidden' }}>
        <Box sx={{ background: 'linear-gradient(135deg,#455A64,#607D8B)', color: '#fff', px: 2.5, py: 1.5,
                   display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
          <DirectionsCar />
          <Typography fontWeight={900} fontSize={16}>نقشه جایگاه‌ها ({yard.length})</Typography>
          <Chip size="small" sx={{ bgcolor: 'rgba(255,255,255,.2)', color: '#fff' }} label={`آزاد ${free}`} />
          <Chip size="small" sx={{ bgcolor: 'rgba(255,255,255,.2)', color: '#fff' }} label={`اشغال ${occ}`} />
          <Box flexGrow={1} />
          <TextField size="small" placeholder="جستجوی شماره…" value={q}
            onChange={(e) => setQ(e.target.value)}
            sx={{ width: 180, bgcolor: 'rgba(255,255,255,.92)', borderRadius: 1 }}
            InputProps={{ startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment> }} />
          <ToggleButtonGroup size="small" exclusive value={filter}
            onChange={(_, v: 'ALL' | 'FREE' | 'OCCUPIED' | null) => v && setFilter(v)}
            sx={{ bgcolor: 'rgba(255,255,255,.92)', borderRadius: 1 }}>
            <ToggleButton value="ALL">همه</ToggleButton>
            <ToggleButton value="FREE">آزاد</ToggleButton>
            <ToggleButton value="OCCUPIED">اشغال</ToggleButton>
          </ToggleButtonGroup>
        </Box>
        <CardContent sx={{ pt: 2 }}>
          {groups.map(([pre, list]) => {
            const vis = list.filter((s) => visible.includes(s))
            if (vis.length === 0) return null
            return (
              <Box key={pre} mb={2}>
                <Stack direction="row" spacing={1} alignItems="center" mb={1}>
                  <Chip size="small" color="primary" label={`گروه ${pre}`} />
                  <Chip size="small" variant="outlined" label={`${list.length} جایگاه`} />
                </Stack>
                <Box sx={{ display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(110px, 1fr))', gap: 1 }}>
                  {vis.map((s) => {
                    const m = meta(s.status)
                    return (
                      <Tooltip key={s.id} title={s.status === 'FREE' ? 'کلیک برای حذف' : 'اشغال — حذف ممکن نیست'}>
                        <Box onClick={() => { if (s.status === 'FREE') del.mutate(s.id) }}
                          sx={{ borderRadius: 2, p: 1.2, textAlign: 'center', cursor: s.status === 'FREE' ? 'pointer' : 'default',
                            background: m.bg, border: `2px solid ${m.border}`,
                            transition: 'transform .12s', '&:hover': { transform: s.status === 'FREE' ? 'translateY(-3px)' : 'none', boxShadow: 3 } }}>
                          <DirectionsCar sx={{ fontSize: 26, color: m.border }} />
                          <Typography sx={{ fontFamily: 'monospace', direction: 'ltr', fontWeight: 900, fontSize: 13, color: m.text }}>
                            {s.code}
                          </Typography>
                          <Typography variant="caption" sx={{ color: m.text }}>{m.fa}</Typography>
                        </Box>
                      </Tooltip>
                    )
                  })}
                </Box>
              </Box>
            )
          })}
          {yard.length === 0 && (
            <Alert severity="info">هنوز جایگاهی ثبت نشده — از کارت بالا با تعیین پیش‌وند و تعداد شروع کنید.</Alert>
          )}
          {yard.length > 0 && visible.length === 0 && (
            <Alert severity="warning">موردی با این جستجو/فیلتر پیدا نشد.</Alert>
          )}
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
            کلیک روی جایگاه آزاد = حذف (با تایید مرورگر) | جایگاه اشغال حذف نمی‌شود — تاریخچه حفظ است.
          </Typography>
        </CardContent>
      </Card>
    </Stack>
  )
}
