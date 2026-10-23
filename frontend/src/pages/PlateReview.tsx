import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, Box, Button, Card, CardContent, Chip, CircularProgress, Dialog, DialogActions,
  DialogContent, DialogTitle, MenuItem, Stack, Tab, Tabs, TextField, Typography,
} from '@mui/material'
import { Verified } from '@mui/icons-material'
import { api, apiErrorFa } from '../api/client'
import PlateBox from '../components/PlateBox'

interface ReviewRow {
  id: string
  gate_id: string
  direction: string
  plate_raw: string
  plate_normalized: string | null
  plate_corrected: string | null
  confidence: number | null
  review_status: string
  capture_quality: {
    angle_deg?: number
    lux?: number
    speed_kmh?: number
    envelope_ok?: boolean
    envelope_violations?: string[]
    thresholds?: Record<string, number>
  } | null
  correction_note: string | null
  captured_at: string | null
  received_at: string | null
}

interface Metrics {
  counts: Record<string, number>
  processing_ms: { p50: number | null; p95: number | null; target_p95_ms: number; n: number }
}

const STATUS_FA: Record<string, string> = {
  AUTO_OK: 'خودکار',
  NEEDS_REVIEW: 'نیازمند تأیید',
  CONFIRMED: 'تأییدشده',
  CORRECTED: 'اصلاح‌شده',
  REJECTED: 'ردشده',
}

const VIOLATION_FA: Record<string, string> = {
  ANGLE: 'زاویه خارج از پاکت',
  LUX: 'نور ناکافی',
  SPEED: 'سرعت خارج از محدوده',
}

export default function PlateReview() {
  const qc = useQueryClient()
  const [tab, setTab] = useState('NEEDS_REVIEW')
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [target, setTarget] = useState<ReviewRow | null>(null)
  const [action, setAction] = useState('CORRECT')
  const [plate, setPlate] = useState('')
  const [note, setNote] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['plate-reviews', tab],
    queryFn: async () => (await api.get(`/gate/plate-reviews?status=${tab}`)).data as { status: string; total: number; items: ReviewRow[] },
  })
  const { data: metrics } = useQuery({
    queryKey: ['plate-review-metrics'],
    queryFn: async () => (await api.get('/gate/plate-reviews/metrics')).data as Metrics,
  })

  const resolve = useMutation({
    mutationFn: async () => (await api.post(`/gate/plate-reviews/${target!.id}/resolve`, {
      action, plate_raw: action === 'CORRECT' ? plate : null, note: note || null,
    })).data as { review_status: string },
    onSuccess: (d) => {
      setMsg(`ثبت شد: ${STATUS_FA[d.review_status] ?? d.review_status} — مقدار اصلی حفظ و اصلاح جداگانه ثبت شد.`)
      setTarget(null); setPlate(''); setNote('')
      qc.invalidateQueries()
    },
    onError: (e) => setErr(apiErrorFa(e)),
  })

  const openDialog = (row: ReviewRow, act: string) => {
    setTarget(row)
    setAction(act)
    setPlate(act === 'CORRECT' ? (row.plate_corrected ?? row.plate_raw ?? '') : '')
    setNote('')
  }

  return (
    <Box>
      <Typography variant="h5" fontWeight={900} mb={1}>
        🔎 بازبینی پلاک — مسیر تأیید انسانی
      </Typography>
      <Typography variant="body2" color="text.secondary" mb={2}>
        پلاک‌های «ثبت‌نشده» یا کم‌اطمینان (خارج از پاکت زاویه/نور/سرعت) اینجا تعیین تکلیف می‌شوند.
        مقدار اصلی خوانده‌شده همیشه حفظ و اصلاح به‌صورت جداگانه با نام کاربر ثبت می‌شود.
      </Typography>

      {msg && <Alert severity="success" sx={{ mb: 2 }} onClose={() => setMsg('')}>{msg}</Alert>}
      {err && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErr('')}>{err}</Alert>}

      {/* متریک‌ها */}
      {metrics && (
        <Card variant="outlined" sx={{ borderRadius: 3, mb: 2 }}>
          <CardContent>
            <Stack direction="row" spacing={3} flexWrap="wrap">
              <Box>
                <Typography fontWeight={900} color={metrics.processing_ms.p95 !== null && metrics.processing_ms.p95 <= metrics.processing_ms.target_p95_ms ? 'success.main' : 'warning.main'}>
                  p95 = {metrics.processing_ms.p95 !== null ? `${metrics.processing_ms.p95}ms` : '—'}
                </Typography>
                <Typography variant="caption" color="text.secondary">هدف الحاقیه: p95 &lt; ۱۰۰۰ms (ن={metrics.processing_ms.n})</Typography>
              </Box>
              <Box><Typography fontWeight={800}>{metrics.counts.AUTO_OK ?? 0}</Typography><Typography variant="caption">خودکار</Typography></Box>
              <Box><Typography fontWeight={800} color="warning.main">{metrics.counts.NEEDS_REVIEW ?? 0}</Typography><Typography variant="caption">در انتظار تأیید</Typography></Box>
              <Box><Typography fontWeight={800}>{metrics.counts.CORRECTED ?? 0}</Typography><Typography variant="caption">اصلاح‌شده</Typography></Box>
              <Box><Typography fontWeight={800}>{metrics.counts.REJECTED ?? 0}</Typography><Typography variant="caption">ردشده</Typography></Box>
            </Stack>
          </CardContent>
        </Card>
      )}

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        {['NEEDS_REVIEW', 'AUTO_OK', 'CONFIRMED', 'CORRECTED', 'REJECTED'].map((s) => (
          <Tab key={s} value={s} label={`${STATUS_FA[s]} (${s === tab ? data?.total ?? 0 : ''})`} />
        ))}
      </Tabs>

      {isLoading && <CircularProgress />}
      {(data?.items ?? []).length === 0 && !isLoading && (
        <Typography color="text.secondary">موردی در این وضعیت نیست ✅</Typography>
      )}

      <Stack spacing={1.5}>
        {(data?.items ?? []).map((r) => (
          <Card key={r.id} variant="outlined" sx={{ borderRadius: 3 }}>
            <CardContent>
              <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap">
                <PlateBox plate={r.plate_corrected ?? r.plate_normalized ?? r.plate_raw} size="md" />
                <Box sx={{ minWidth: 220 }}>
                  <Typography variant="caption" component="div">
                    اطمینان: <b>{r.confidence !== null ? `${Math.round(r.confidence * 100)}٪` : '—'}</b>
                  </Typography>
                  <Typography variant="caption" component="div" color="text.secondary">
                    جهت: {r.direction === 'IN' ? 'ورود' : 'خروج'} | زمان: {r.received_at ? new Date(r.received_at).toLocaleString('fa-IR') : '—'}
                  </Typography>
                  {r.capture_quality && (
                    <Typography variant="caption" component="div" color="text.secondary">
                      زاویه: {r.capture_quality.angle_deg ?? '—'}° | نور: {r.capture_quality.lux ?? '—'} | سرعت: {r.capture_quality.speed_kmh ?? '—'}
                    </Typography>
                  )}
                </Box>
                <Box sx={{ flex: 1, minWidth: 180 }}>
                  {r.capture_quality?.envelope_violations?.map((v) => (
                    <Chip key={v} size="small" color="warning" sx={{ ml: 0.5, mb: 0.5 }}
                      label={VIOLATION_FA[v.split(':')[0]] ?? v} />
                  ))}
                  {r.review_status === 'NEEDS_REVIEW' && (
                    <Typography variant="caption" color="warning.dark" component="div" fontWeight={800}>
                      پلاک «ثبت‌نشده» — عبور فقط با تأیید انسانی
                    </Typography>
                  )}
                  {r.correction_note && (
                    <Typography variant="caption" color="text.secondary" component="div">
                      یادداشت: {r.correction_note}
                    </Typography>
                  )}
                </Box>
                {r.review_status === 'NEEDS_REVIEW' && (
                  <Stack direction="row" spacing={1}>
                    <Button size="small" variant="contained" color="success" startIcon={<Verified />}
                      onClick={() => openDialog(r, 'CONFIRM')}>
                      تأیید همان مقدار
                    </Button>
                    <Button size="small" variant="outlined" onClick={() => openDialog(r, 'CORRECT')}>
                      اصلاح
                    </Button>
                    <Button size="small" color="error" onClick={() => openDialog(r, 'REJECT')}>
                      رد
                    </Button>
                  </Stack>
                )}
              </Stack>
            </CardContent>
          </Card>
        ))}
      </Stack>

      <Dialog open={target !== null} onClose={() => setTarget(null)} maxWidth="sm" fullWidth>
        <DialogTitle>
          {action === 'CONFIRM' ? 'تأیید پلاک' : action === 'CORRECT' ? 'اصلاح پلاک' : 'رد خوانش'}
        </DialogTitle>
        <DialogContent>
          <Typography variant="caption" component="div" color="text.secondary">
            مقدار اصلی (حفظ می‌شود): <b style={{ direction: 'ltr' }}>{target?.plate_raw}</b>
          </Typography>
          {action === 'CORRECT' && (
            <TextField
              autoFocus fullWidth margin="dense" label="پلاک اصلاح‌شده"
              value={plate} onChange={(e) => setPlate(e.target.value)}
              placeholder="مثال: 12 ب 345 ایران 11"
            />
          )}
          {action === 'REJECT' && (
            <Alert severity="warning" sx={{ mt: 1 }}>
              خوانش رد می‌شود و در صف باقی نخواهد ماند؛ تصمیم مربوطه در گزارش بازبینی می‌ماند.
            </Alert>
          )}
          <TextField
            select fullWidth margin="dense" label="عملیات" value={action}
            onChange={(e) => setAction(e.target.value)}
          >
            <MenuItem value="CONFIRM">تأیید مقدار خوانده‌شده</MenuItem>
            <MenuItem value="CORRECT">اصلاح پلاک (تایپ دستی)</MenuItem>
            <MenuItem value="REJECT">رد خوانش</MenuItem>
          </TextField>
          <TextField
            fullWidth margin="dense" multiline rows={2} label="یادداشت"
            value={note} onChange={(e) => setNote(e.target.value)}
          />
          <Typography variant="caption" color="text.secondary">
            هر تغییر با نام کاربری، زمان و یادداشت در تاریخچه (audit) ثبت می‌شود.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setTarget(null)}>انصراف</Button>
          <Button
            variant="contained"
            disabled={resolve.isPending || (action === 'CORRECT' && !plate.trim())}
            onClick={() => resolve.mutate()}
          >
            ثبت
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
