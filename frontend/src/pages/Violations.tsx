import { useState, useEffect, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem,
  Stack, TextField, Typography,
} from '@mui/material'
import { api, apiErrorFa } from '../api/client'
import { faDate, money } from '../utils/format'

function ViolationImage({ fileId }: { fileId: string }) {
  const [url, setUrl] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    let dead = false
    api.get(`/files/${fileId}/url`)
      .then((r) => { if (!dead) setUrl(r.data.url) })
      .catch(() => { if (!dead) setFailed(true) })
    return () => { dead = true }
  }, [fileId])
  if (failed) return <Typography variant="caption" color="error">تصویر در دسترس نیست</Typography>
  if (!url) return <Typography variant="caption" color="text.secondary">در حال بارگذاری تصویر...</Typography>
  return (
    <Box component="img" src={url} alt="violation"
      sx={{ maxWidth: 320, maxHeight: 220, borderRadius: 2, border: '2px solid #E3EAF2' }} />
  )
}

export default function Violations() {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [plate, setPlate] = useState('')
  const [vtype, setVtype] = useState('WRONG_PARKING')
  const [desc, setDesc] = useState('')
  const [error, setError] = useState('')

  const { data: violations } = useQuery({
    queryKey: ['violations'],
    queryFn: async () => (await api.get('/violations')).data,
  })
  const { data: types } = useQuery({
    queryKey: ['violation-types'],
    queryFn: async () => (await api.get('/violations/types')).data as Record<string, unknown>[],
  })

  const create = useMutation({
    mutationFn: async () => (await api.post('/violations', {
      plate_raw: plate, violation_type_code: vtype, description: desc || null,
    })).data,
    onSuccess: () => { setOpen(false); setPlate(''); setDesc(''); setError(''); qc.invalidateQueries({ queryKey: ['violations'] }) },
    onError: (err) => setError(apiErrorFa(err)),
  })

  const act = useMutation({
    mutationFn: async (p: { id: string; action: 'confirm' | 'cancel'; reason?: string }) =>
      (await api.post(`/violations/${p.id}/${p.action}`, { reason: p.reason })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['violations'] }),
    onError: (err) => setError(apiErrorFa(err)),
  })

  const submit = (e: FormEvent) => { e.preventDefault(); setError(''); create.mutate() }
  const typeTitle = (id: string) => String((types ?? []).find((t) => t.id === id)?.title ?? id)

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between">
        <Typography variant="h6" fontWeight={800}>تخلفات</Typography>
        <Button variant="contained" color="error" onClick={() => setOpen(true)}>ثبت تخلف</Button>
      </Stack>
      {error && <Alert severity="error">{error}</Alert>}

      {(violations ?? []).map((v: Record<string, unknown>) => (
        <Stack key={v.id as string} spacing={1}
          sx={{ bgcolor: '#fff', borderRadius: 3, p: 2, border: '1px solid #E0E0E0' }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
            <Stack>
              <Typography fontWeight={800}>{String(v.plate_normalized ?? '—')}</Typography>
              <Typography variant="body2" color="text.secondary">
                {typeTitle(String(v.violation_type_id))} — {money(v.penalty_amount as number)} — {faDate(v.occurred_at as string)}
              </Typography>
            </Stack>
            <Stack direction="row" spacing={1} alignItems="center">
              <Chip size="small" label={String(v.status)} color={
                v.status === 'CONFIRMED' ? 'error' : v.status === 'CANCELLED' ? 'default' : 'warning'} />
              {v.status === 'REGISTERED' ? (
                <>
                  <Button size="small" variant="contained" color="error"
                    onClick={() => act.mutate({ id: v.id as string, action: 'confirm' })}>تأیید</Button>
                  <Button size="small" variant="outlined" onClick={() => {
                    const reason = window.prompt('دلیل ابطال تخلف:')
                    if (reason) act.mutate({ id: v.id as string, action: 'cancel', reason })
                  }}>ابطال</Button>
                </>
              ) : null}
            </Stack>
          </Stack>
          {v.image_file_id ? <ViolationImage fileId={String(v.image_file_id)} /> : null}
        </Stack>
      ))}
      {violations?.length === 0 ? <Typography color="text.secondary">تخلفی ثبت نشده است.</Typography> : null}

      <Dialog open={open} onClose={() => setOpen(false)}>
        <DialogTitle>ثبت تخلف</DialogTitle>
        <form onSubmit={submit}>
          <DialogContent>
            {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
            <TextField fullWidth label="پلاک" value={plate} onChange={(e) => setPlate(e.target.value)} margin="normal" required />
            <TextField fullWidth select label="نوع تخلف" value={vtype} onChange={(e) => setVtype(e.target.value)} margin="normal">
              {(types ?? []).map((t) => (
                <MenuItem key={String(t.code)} value={String(t.code)}>
                  {String(t.title)} ({money(t.default_penalty_amount as number)})
                </MenuItem>
              ))}
            </TextField>
            <TextField fullWidth label="توضیحات" value={desc} onChange={(e) => setDesc(e.target.value)} margin="normal" />
            <Typography variant="caption" color="text.secondary">
              برای ثبت همراه با عکس، از «پنل مسئول محوطه» استفاده کنید.
            </Typography>
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