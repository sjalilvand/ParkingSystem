import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Stack,
  TextField, Typography,
} from '@mui/material'
import { api, apiErrorFa } from '../api/client'
import { money } from '../utils/format'

export default function Tariffs() {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState('')
  const [freeMin, setFreeMin] = useState('15')
  const [hourly, setHourly] = useState('10000')
  const [dailyCap, setDailyCap] = useState('')
  const [error, setError] = useState('')

  const { data } = useQuery({
    queryKey: ['tariffs'],
    queryFn: async () => (await api.get('/tariffs')).data as Record<string, unknown>[],
  })

  const create = useMutation({
    mutationFn: async () => (await api.post('/tariffs', {
      title,
      free_minutes: parseInt(freeMin) || 0,
      hourly_amount: parseInt(hourly) || 0,
      daily_max_amount: dailyCap ? parseInt(dailyCap) : null,
    })).data,
    onSuccess: () => { setOpen(false); setTitle(''); setError(''); qc.invalidateQueries({ queryKey: ['tariffs'] }) },
    onError: (err) => setError(apiErrorFa(err)),
  })

  const activate = useMutation({
    mutationFn: async (id: string) => (await api.post(`/tariffs/${id}/activate`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tariffs'] }),
  })

  const submit = (e: FormEvent) => { e.preventDefault(); setError(''); create.mutate() }

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between">
        <Typography variant="h6">تعرفه‌ها</Typography>
        <Button variant="contained" onClick={() => setOpen(true)}>تعرفه جدید</Button>
      </Stack>
      {error && <Alert severity="error">{error}</Alert>}

      {(data ?? []).map((t) => (
        <Stack key={t.id as string} direction="row" justifyContent="space-between" alignItems="center"
          sx={{ bgcolor: '#fff', borderRadius: 2, p: 2, border: '1px solid #E0E0E0' }}>
          <Stack>
            <Typography fontWeight={800}>{String(t.title)}</Typography>
            <Typography variant="body2" color="text.secondary">
              رایگان: {String(t.free_minutes)} دقیقه — ساعتی: {money(t.hourly_amount as number)}
              {t.daily_max_amount ? ` — سقف روزانه: ${money(t.daily_max_amount as number)}` : ''}
            </Typography>
          </Stack>
          {t.status === 'ACTIVE'
            ? <Chip color="success" label="فعال" />
            : <Button size="small" variant="outlined" onClick={() => activate.mutate(t.id as string)}>فعال‌سازی</Button>}
        </Stack>
      ))}

      <Dialog open={open} onClose={() => setOpen(false)}>
        <DialogTitle>تعرفه جدید</DialogTitle>
        <form onSubmit={submit}>
          <DialogContent>
            {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
            <TextField fullWidth label="عنوان" value={title} onChange={(e) => setTitle(e.target.value)} margin="normal" required />
            <TextField fullWidth label="دقایق رایگان" type="number" value={freeMin} onChange={(e) => setFreeMin(e.target.value)} margin="normal" />
            <TextField fullWidth label="مبلغ ساعتی (ریال)" type="number" value={hourly} onChange={(e) => setHourly(e.target.value)} margin="normal" />
            <TextField fullWidth label="سقف روزانه (اختیاری)" type="number" value={dailyCap} onChange={(e) => setDailyCap(e.target.value)} margin="normal" />
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setOpen(false)}>انصراف</Button>
            <Button type="submit" variant="contained" disabled={create.isPending}>ثبت</Button>
          </DialogActions>
        </form>
      </Dialog>
    </Stack>
  )
}