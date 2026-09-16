import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, Box, Button, Card, CardContent, Chip, Dialog, DialogActions, DialogContent,
  DialogTitle, MenuItem, Stack, TextField, Typography,
} from '@mui/material'
import { api, apiErrorFa } from '../api/client'
import { jalaliDisplay } from '../utils/jalali'
import { faDate } from '../utils/format'
import PlateBox from '../components/PlateBox'
import PlateInput from '../components/PlateInput'
import JalaliDateInput from '../components/JalaliDateInput'

interface PermitRow {
  id: string; plate_normalized: string; permit_type: string; status: string
  valid_until?: string | null; used_entries: number; max_entries?: number | null
  reason?: string | null
}
interface Unit { id: string; unit_number: string }
interface Tower { id: string; name: string }

const PERMIT_TYPES = [
  { code: 'GUEST', fa: 'مهمان' }, { code: 'TEMPORARY', fa: 'موقت' },
  { code: 'CONTRACTOR', fa: 'پیمانکار' }, { code: 'SERVICE', fa: 'خدماتی' },
  { code: 'PERMANENT', fa: 'دائمی' },
]

export default function Permits() {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')

  const [plate, setPlate] = useState('')
  const [ptype, setPtype] = useState('GUEST')
  const [untilIso, setUntilIso] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const [hostUnit, setHostUnit] = useState('')

  const { data } = useQuery({
    queryKey: ['permits'],
    queryFn: async () => (await api.get('/permits', { params: { page_size: 50 } })).data as { items: PermitRow[] },
  })
  const { data: towers } = useQuery({ queryKey: ['towers'], queryFn: async () => (await api.get('/towers')).data as Tower[] })
  const [towerId, setTowerId] = useState('')
  const activeTower = towerId || towers?.[0]?.id || ''
  const { data: units } = useQuery({
    queryKey: ['units', activeTower],
    queryFn: async () => (await api.get('/units', { params: { tower_id: activeTower || undefined } })).data as Unit[],
    enabled: !!activeTower,
  })

  const create = useMutation({
    mutationFn: async (e: FormEvent) => {
      e.preventDefault()
      return (await api.post('/permits', {
        plate_raw: plate,
        permit_type: ptype,
        valid_until: untilIso,
        host_unit_id: hostUnit || null,
        reason: reason || null,
      })).data
    },
    onSuccess: () => {
      setOpen(false); setPlate(''); setReason(''); setUntilIso(null); setHostUnit(''); setErr('')
      setMsg('مجوز صادر شد')
      qc.invalidateQueries({ queryKey: ['permits'] })
    },
    onError: (e) => setErr(apiErrorFa(e)),
  })

  const act = useMutation({
    mutationFn: async (p: { id: string; action: 'activate' | 'revoke' }) =>
      (await api.post(`/permits/${p.id}/${p.action}`)).data,
    onSuccess: () => { setErr(''); qc.invalidateQueries({ queryKey: ['permits'] }) },
    onError: (e) => setErr(apiErrorFa(e)),
  })

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h6" fontWeight={800}>مجوزهای تردد</Typography>
        <Button variant="contained" onClick={() => { setErr(''); setOpen(true) }}>صدور مجوز جدید</Button>
      </Stack>

      {msg && <Alert severity="success">{msg}</Alert>}
      {err && <Alert severity="error">{err}</Alert>}

      {(data?.items ?? []).map((p) => (
        <Card key={p.id}>
          <CardContent sx={{ py: 2 }}>
            <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1.5}>
              <Stack spacing={1} alignItems="flex-start">
                <PlateBox plate={p.plate_normalized} />
                <Typography variant="body2" color="text.secondary">
                  {PERMIT_TYPES.find((t) => t.code === p.permit_type)?.fa ?? p.permit_type}
                  {p.valid_until ? ` — اعتبار تا: ${jalaliDisplay(p.valid_until, true)}` : ''}
                  {p.reason ? ` — ${p.reason}` : ''}
                </Typography>
              </Stack>
              <Stack direction="row" spacing={1} alignItems="center">
                <Chip size="small" label={`${p.used_entries}/${p.max_entries ?? '∞'}`} />
                <Chip size="small" color={p.status === 'ACTIVE' ? 'success' : 'default'} label={p.status === 'ACTIVE' ? 'فعال' : 'لغو شده'} />
                {p.status === 'ACTIVE' ? (
                  <Button size="small" color="warning" onClick={() => act.mutate({ id: p.id, action: 'revoke' })}>لغو</Button>
                ) : (
                  <Button size="small" color="success" onClick={() => act.mutate({ id: p.id, action: 'activate' })}>فعال‌سازی</Button>
                )}
              </Stack>
            </Stack>
          </CardContent>
        </Card>
      ))}
      {data?.items?.length === 0 && <Alert severity="info">مجوزی صادر نشده است.</Alert>}

      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>صدور مجوز جدید</DialogTitle>
        <form onSubmit={(e) => create.mutate(e)}>
          <DialogContent>
            {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}

            <Typography variant="caption" color="text.secondary" mb={0.5} display="block">پلاک خودرو</Typography>
            <PlateInput raw={plate} onChange={setPlate} />
            {plate.trim() ? (
              <Stack alignItems="center" my={1.5}>
                <PlateBox plate={plate} />
              </Stack>
            ) : null}

            <TextField fullWidth select label="نوع مجوز" value={ptype}
              onChange={(e) => setPtype(e.target.value)} margin="normal">
              {PERMIT_TYPES.map((t) => <MenuItem key={t.code} value={t.code}>{t.fa}</MenuItem>)}
            </TextField>

            <Box mt={2}>
              <JalaliDateInput label="اعتبار تا" value={untilIso} onChange={setUntilIso} includeTime />
            </Box>

            <TextField fullWidth select label="واحد میزبان (اختیاری)" value={hostUnit}
              onChange={(e) => setHostUnit(e.target.value)} margin="normal">
              <MenuItem value="">—</MenuItem>
              {(units ?? []).map((u) => <MenuItem key={u.id} value={u.id}>واحد {u.unit_number}</MenuItem>)}
            </TextField>
            <TextField fullWidth select label="برج (برای فهرست واحدها)" value={activeTower}
              onChange={(e) => setTowerId(e.target.value)} margin="normal">
              {(towers ?? []).map((t) => <MenuItem key={t.id} value={t.id}>{t.name}</MenuItem>)}
            </TextField>

            <TextField fullWidth label="علت صدور" value={reason}
              onChange={(e) => setReason(e.target.value)} margin="normal" />
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setOpen(false)}>انصراف</Button>
            <Button type="submit" variant="contained" disabled={create.isPending || !plate.trim()}>
              صدور مجوز
            </Button>
          </DialogActions>
        </form>
      </Dialog>
    </Stack>
  )
}