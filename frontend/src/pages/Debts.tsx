import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, CardContent, Stack, TextField, Typography, Chip } from '@mui/material'
import { api, apiErrorFa } from '../api/client'
import { faDate, money } from '../utils/format'

export default function Debts() {
  const qc = useQueryClient()
  const [plate, setPlate] = useState('')
  const [msg, setMsg] = useState('')
  const [error, setError] = useState('')

  const { data } = useQuery({
    queryKey: ['debts', plate],
    queryFn: async () => (await api.get('/debts', { params: { plate: plate || undefined } })).data,
  })

  const pay = useMutation({
    mutationFn: async (p: { chargeAmount: number; plateRaw: string }) => (await api.post('/payments', {
      plate_raw: p.plateRaw || plate || null,
      amount: p.chargeAmount,
      reference_number: `WEB-${Date.now()}`,
    })).data,
    onSuccess: (r) => {
      setMsg(`پرداخت ${r.reference_number} ثبت شد`)
      setError('')
      qc.invalidateQueries({ queryKey: ['debts'] })
    },
    onError: (err) => setError(apiErrorFa(err)),
  })

  return (
    <Stack spacing={2}>
      <Typography variant="h6">بدهی‌های پرداخت‌نشده</Typography>
      <TextField size="small" placeholder="فیلتر پلاک (اختیاری)" value={plate} onChange={(e) => setPlate(e.target.value)} sx={{ width: 320 }} />
      {msg && <Alert severity="success">{msg}</Alert>}
      {error && <Alert severity="error">{error}</Alert>}
      <Card>
        <CardContent>
          <Chip label={`جمع کل: ${money(data?.total_unpaid)}`} color="warning" sx={{ mb: 2 }} />
          {(data?.items ?? []).map((d: Record<string, unknown>) => (
            <Stack key={d.charge_id as string} direction="row" justifyContent="space-between" alignItems="center"
              sx={{ py: 1.5, borderBottom: '1px solid #EEE' }}>
              <Stack>
                <Typography fontWeight={700}>
                  {d.charge_type === 'PARKING' ? 'توقف پارکینگ' : 'جریمه تخلف'} — {money(d.amount as number)}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  پلاک: {String(d.plate ?? '—')} — {faDate(d.created_at as string)}
                </Typography>
              </Stack>
              <Button variant="contained" size="small" color="success"
                onClick={() => pay.mutate({ chargeAmount: d.amount as number, plateRaw: String(d.plate ?? plate ?? '') })}>
                تسویه
              </Button>
            </Stack>
          ))}
          {data?.items?.length === 0 && <Typography color="text.secondary">بدهی پرداخت‌نشده‌ای وجود ندارد ✔</Typography>}
        </CardContent>
      </Card>
    </Stack>
  )
}