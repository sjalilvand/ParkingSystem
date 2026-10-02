import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, Box, Button, Card, CardContent, Chip, Stack, TextField, Typography,
} from '@mui/material'
import { Delete, Add } from '@mui/icons-material'
import { api, apiErrorFa } from '../api/client'

interface Space { id: string; code: string; zone: string | null; parking_type: string; status: string; is_active: boolean }
interface Cap { declared_capacity: number | null; capacity_source: string; registered_yard_count: number; confirmed_presence: number; available: number | null; accepting: boolean }

export default function YardManager() {
  const qc = useQueryClient()
  const [err, setErr] = useState(''); const [msg, setMsg] = useState('')
  const [prefix, setPrefix] = useState('Y'); const [count, setCount] = useState(10)
  const [capDraft, setCapDraft] = useState<number | null>(null)

  const { data: spaces } = useQuery({
    queryKey: ['ps-all'], queryFn: async () => (await api.get('/parking-spaces')).data as Space[],
  })
  const { data: cap } = useQuery({
    queryKey: ['cap-status'], queryFn: async () => (await api.get('/parking/capacity-status')).data as Cap,
  })
  const yard = (spaces ?? []).filter((s) => s.parking_type === 'YARD')

  const invalidate = () => qc.invalidateQueries({ queryKey: ['ps-all', 'cap-status'] })

  const bulk = useMutation({
    mutationFn: async () => (await api.post('/parking/yard-spaces', { count, prefix })).data as
      { created: string[]; skipped_existing: string[] },
    onSuccess: (d) => {
      setErr(''); setMsg(`${d.created.length} جایگاه ساخته شد` +
        (d.skipped_existing.length ? ` — ${d.skipped_existing.length} مورد از قبل موجود بود` : ''))
      invalidate()
    },
    onError: (e) => setErr(apiErrorFa(e)),
  })
  const del = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/parking/yard-spaces/${id}`)).data,
    onSuccess: () => { setErr(''); setMsg('حذف شد'); invalidate() },
    onError: (e) => setErr(apiErrorFa(e)),
  })
  const saveCap = useMutation({
    mutationFn: async (total: number) =>
      (await api.put('/app-settings/yard_capacity', { value: { total }, reason: 'yard-manager' })).data,
    onSuccess: () => { setErr(''); setMsg('ظرفیت محوطه ذخیره شد — از همین لحظه در موتور ورود اعمال می‌شود'); invalidate() },
    onError: (e) => setErr(apiErrorFa(e)),
  })

  const preview = Array.from({ length: Math.min(count, 500) }, (_, i) => {
    const w = Math.max(2, String(count).length)
    return `${prefix.trim() || 'Y'}-${String(i + 1).padStart(w, '0')}`
  })

  return (
    <Stack spacing={2}>
      {err && <Alert severity="error">{err}</Alert>}
      {msg && <Alert severity="success">{msg}</Alert>}

      <Card><CardContent>
        <Typography fontWeight={800} mb={1}>ثبت پارکینگ‌های محوطه (شماره‌گذاری خودکار)</Typography>
        <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap alignItems="center">
          <TextField size="small" label="پیش‌وند" value={prefix} sx={{ width: 110 }}
            onChange={(e) => setPrefix(e.target.value)} />
          <TextField size="small" type="number" label="تعداد" value={String(count)} sx={{ width: 110 }}
            onChange={(e) => setCount(Math.max(1, Math.min(500, Number(e.target.value) || 1)))} />
          <Button variant="contained" startIcon={<Add />} disabled={bulk.isPending}
            onClick={() => bulk.mutate()}>ثبت / تکمیل</Button>
          {preview.length > 0 && (
            <Typography variant="caption" color="text.secondary">
              نمونه: {preview.slice(0, 3).join('، ')}{preview.length > 3 ? ' …' : ''}
            </Typography>
          )}
        </Stack>
        <Typography variant="caption" color="text.secondary">
          اجرای دوباره بی‌خطر است: شماره‌های موجود دوباره ساخته نمی‌شوند (فقط کمبودها ساخته می‌شوند).
        </Typography>
      </CardContent></Card>

      <Card><CardContent>
        <Typography fontWeight={800} mb={1}>ظرفیت اعلامی محوطه (منبع موتور ورود)</Typography>
        <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap alignItems="center">
          <TextField size="small" type="number" label="ظرفیت (خودرو)" sx={{ width: 150 }}
            value={String(capDraft ?? cap?.declared_capacity ?? '')}
            onChange={(e) => setCapDraft(Number(e.target.value) || 0)} />
          <Button variant="contained" disabled={saveCap.isPending}
            onClick={() => saveCap.mutate(Number(capDraft ?? cap?.declared_capacity ?? 0))}>ذخیره ظرفیت</Button>
          {cap && (
            <>
              <Chip size="small" variant="outlined"
                label={`منبع: ${cap.capacity_source === 'setting' ? 'طراح' : cap.capacity_source === 'env' ? 'env' : 'نامحدود'}`} />
              <Chip size="small" variant="outlined" label={`حضور: ${cap.confirmed_presence}`} />
              <Chip size="small" color={cap.accepting ? 'success' : 'error'}
                label={cap.accepting ? 'پذیرش باز' : 'ظرفیت پر'} />
            </>
          )}
        </Stack>
        <Typography variant="caption" color="text.secondary">
          این عدد در موتور ورود زنده اعمال می‌شود (در ظرفیت کامل: تصمیم با اپراتور، نه بستن خودکار).
        </Typography>
      </CardContent></Card>

      <Card><CardContent>
        <Typography fontWeight={800} mb={1}>جایگاه‌های ثبت‌شده ({yard.length})</Typography>
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
          {yard.map((s) => (
            <Chip key={s.id}
              label={s.code}
              color={s.status === 'OCCUPIED' ? 'error' : s.status === 'FREE' ? 'success' : 'default'}
              variant={s.status === 'OCCUPIED' ? 'filled' : 'outlined'}
              onDelete={s.status === 'FREE' ? () => del.mutate(s.id) : undefined} />
          ))}
          {yard.length === 0 && <Typography color="text.secondary">هنوز جایگاه محوطه‌ای ثبت نشده است.</Typography>}
        </Box>
        <Typography variant="caption" color="text.secondary">
          قرمز = اشغال (قابل حذف نیست) | سبز = آزاد (حذف با ضربدر) — تاریخچهٔ تخصیص‌های بسته‌شده حفظ می‌شود.
        </Typography>
      </CardContent></Card>
    </Stack>
  )
}
