import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, Box, Button, Card, CardContent, Chip, CircularProgress, Dialog, DialogActions,
  DialogContent, DialogTitle, Divider, MenuItem, Stack, TextField, Tooltip, Typography,
} from '@mui/material'
import { CloudSync, PlayArrow, Sync } from '@mui/icons-material'
import { api, apiErrorFa } from '../api/client'

interface SyncConfig {
  enabled: boolean
  spreadsheet_id: string
  worksheet: string
  service_account: string
  sync_hour_tehran: number
  max_rows: number
  key_fields: string[]
  columns: string[]
  readonly: boolean
}

interface RunRow {
  id: string
  trigger: string
  status: string
  started_at: string | null
  finished_at: string | null
  rows_total: number
  rows_created: number
  rows_updated: number
  rows_skipped: number
  conflicts_count: number
  error: string | null
}

interface ConflictRow {
  id: string
  row_number: number | null
  external_vehicle_id: string | null
  source_system: string | null
  conflict_type: string
  message: string | null
  incoming: Record<string, unknown> | null
  current: Record<string, unknown> | null
  status: string
  resolution_note: string | null
}

interface Compliance {
  total_vehicles: number
  externally_mapped: number
  unmapped: number
  coverage_pct: number
  pending_conflicts: number
  runs_total: number
  last_run: { id: string; status: string; started_at: string; trigger: string } | null
}

const CONFLICT_FA: Record<string, string> = {
  INVALID_PLATE: 'پلاک نامعتبر',
  INVALID_DATE: 'تاریخ نامعتبر',
  MISSING_REQUIRED: 'فیلد الزامی خالی',
  DUPLICATE_KEY: 'کلید تکراری در شیت',
  PLATE_MISMATCH: 'مغایرت پلاک با سامانه',
  PERMIT_CHANGE: 'تغییر مجوز موجود',
  ROW_ERROR: 'خطای ردیف',
}

const STATUS_FA: Record<string, string> = {
  RUNNING: 'در حال اجرا',
  SUCCESS: 'موفق',
  PARTIAL: 'با تعارض (بخشی)',
  FAILED: 'ناموفق',
}

export default function VehicleSyncPage() {
  const qc = useQueryClient()
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [resolveId, setResolveId] = useState<string | null>(null)
  const [resolveAction, setResolveAction] = useState('SKIP')
  const [resolveNote, setResolveNote] = useState('')

  const { data: cfg } = useQuery({
    queryKey: ['sync-config'],
    queryFn: async () => (await api.get('/integrations/google-sheets/config')).data as SyncConfig,
  })
  const { data: runs } = useQuery({
    queryKey: ['sync-runs'],
    queryFn: async () => (await api.get('/vehicle-sync/runs')).data as { items: RunRow[] },
  })
  const { data: conflicts } = useQuery({
    queryKey: ['sync-conflicts'],
    queryFn: async () => (await api.get('/vehicle-sync/conflicts')).data as { status: string; total: number; items: ConflictRow[] },
  })
  const { data: compliance } = useQuery({
    queryKey: ['sync-compliance'],
    queryFn: async () => (await api.get('/compliance/vehicles')).data as Compliance,
  })

  const test = useMutation({
    mutationFn: async () => (await api.post('/integrations/google-sheets/test')).data as { ok: boolean; title?: string; tabs?: string[]; error?: string },
    onSuccess: (d) => setMsg(d.ok ? `اتصال موفق ✅ «${d.title}» — تب‌ها: ${(d.tabs ?? []).join('، ')}` : `خطا: ${d.error}`),
    onError: (e) => setErr(apiErrorFa(e)),
  })
  const runNow = useMutation({
    mutationFn: async (dry: boolean) =>
      (await api.post(`/integrations/google-sheets/run?dry_run=${dry}`)).data as { status: string; stats?: Record<string, number>; error?: string },
    onSuccess: (d) => {
      setMsg(d.status === 'FAILED'
        ? `اجرای sync ناموفق: ${d.error}`
        : `اجرا شد (${d.status}) — ساخته: ${d.stats?.rows_created ?? 0} | به‌روز: ${d.stats?.rows_updated ?? 0} | تعارض: ${d.stats?.conflicts ?? 0}`)
      qc.invalidateQueries()
    },
    onError: (e) => setErr(apiErrorFa(e)),
  })
  const resolve = useMutation({
    mutationFn: async () => (await api.post(`/vehicle-sync/conflicts/${resolveId}/resolve`, {
      action: resolveAction, note: resolveNote || null,
    })).data as { status: string; applied: boolean },
    onSuccess: (d) => {
      setMsg(`تعارض تعیین تکلیف شد: ${d.status}`)
      setResolveId(null)
      qc.invalidateQueries()
    },
    onError: (e) => setErr(apiErrorFa(e)),
  })

  return (
    <Box>
      <Typography variant="h5" fontWeight={900} mb={1}>
        ☁️ همگام‌سازی خودروها از Google Sheets
      </Typography>
      <Typography variant="body2" color="text.secondary" mb={2}>
        شیت «خودروها» فقط‌خواندنی خوانده می‌شود؛ کلید تطبیق = source_system + external_vehicle_id؛
        اجرای خودکار روزانه ساعت {cfg?.sync_hour_tehran ?? 3}:00 تهران + اجرای دستی. بدهی‌ها، محدودیت‌های داخلی و سابقهٔ تردد هرگز تغییر نمی‌کنند.
      </Typography>

      {msg && <Alert severity="success" sx={{ mb: 2 }} onClose={() => setMsg('')}>{msg}</Alert>}
      {err && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErr('')}>{err}</Alert>}

      {/* پوشش و انطباق */}
      {compliance && (
        <Card variant="outlined" sx={{ borderRadius: 3, mb: 2 }}>
          <CardContent>
            <Stack direction="row" spacing={3} flexWrap="wrap" alignItems="center">
              <Box>
                <Typography variant="h4" fontWeight={900} color="primary">{compliance.coverage_pct}٪</Typography>
                <Typography variant="caption" color="text.secondary">پوشش همگام‌سازی</Typography>
              </Box>
              <Divider orientation="vertical" flexItem />
              <Box><Typography fontWeight={800}>{compliance.total_vehicles}</Typography><Typography variant="caption">کل خودروها</Typography></Box>
              <Box><Typography fontWeight={800}>{compliance.externally_mapped}</Typography><Typography variant="caption">متصل به مبدأ</Typography></Box>
              <Box><Typography fontWeight={800} color={compliance.pending_conflicts ? 'warning.main' : 'success.main'}>{compliance.pending_conflicts}</Typography><Typography variant="caption">تعارض باز</Typography></Box>
              <Box><Typography fontWeight={800}>{compliance.runs_total}</Typography><Typography variant="caption">تعداد اجرا</Typography></Box>
              {compliance.last_run && (
                <Chip
                  size="small"
                  label={`آخرین اجرا: ${STATUS_FA[compliance.last_run.status] ?? compliance.last_run.status} (${compliance.last_run.trigger === 'SCHEDULED' ? 'زمان‌بندی' : 'دستی'})`}
                  color={compliance.last_run.status === 'FAILED' ? 'error' : 'success'}
                />
              )}
            </Stack>
          </CardContent>
        </Card>
      )}

      {/* تنظیمات و اجرا */}
      <Card variant="outlined" sx={{ borderRadius: 3, mb: 2 }}>
        <CardContent>
          <Stack direction="row" spacing={1} alignItems="center" mb={1}>
            <CloudSync color="primary" />
            <Typography fontWeight={900}>اتصال Google Sheets</Typography>
            <Chip size="small" label="فقط‌خواندنی" color="info" />
            {!cfg?.enabled && <Chip size="small" label="غیرفعال" color="default" />}
          </Stack>
          <Typography variant="caption" component="div" sx={{ direction: 'ltr', textAlign: 'left' }}>
            Sheet ID: {cfg?.spreadsheet_id ?? '—'}
          </Typography>
          <Typography variant="caption" color="text.secondary" component="div">
            حساب سرویس: {cfg?.service_account ?? '—'}
          </Typography>
          <Typography variant="caption" color="text.secondary" component="div" mt={1}>
            ستون‌های استاندارد ({cfg?.columns?.length ?? 20}): {(cfg?.columns ?? []).join(' | ')}
          </Typography>
          <Stack direction="row" spacing={1} mt={2} flexWrap="wrap">
            <Button variant="outlined" startIcon={<Sync />} onClick={() => { setErr(''); setMsg(''); test.mutate() }} disabled={test.isPending}>
              تست اتصال
            </Button>
            <Tooltip title="پیش‌نمایش بدون نوشتن در پایگاه‌داده">
              <Button variant="outlined" startIcon={<PlayArrow />} onClick={() => { setErr(''); setMsg(''); runNow.mutate(true) }} disabled={runNow.isPending}>
                اجرای آزمایشی (Dry-run)
              </Button>
            </Tooltip>
            <Button variant="contained" startIcon={runNow.isPending ? <CircularProgress size={16} color="inherit" /> : <CloudSync />}
              onClick={() => { setErr(''); setMsg(''); runNow.mutate(false) }} disabled={runNow.isPending}>
              اجرای همگام‌سازی
            </Button>
          </Stack>
        </CardContent>
      </Card>

      {/* صف تعارض */}
      <Card variant="outlined" sx={{ borderRadius: 3, mb: 2 }}>
        <CardContent>
          <Stack direction="row" alignItems="center" spacing={1} mb={1}>
            <Typography fontWeight={900}>صف تعارض ({conflicts?.total ?? 0})</Typography>
            <Chip size="small" label={conflicts?.status ?? 'PENDING'} color="warning" />
          </Stack>
          {(conflicts?.items ?? []).length === 0 && (
            <Typography color="text.secondary" variant="body2">تعارض بازی وجود ندارد ✅</Typography>
          )}
          <Stack spacing={1}>
            {(conflicts?.items ?? []).map((c) => (
              <Box key={c.id} sx={{ p: 1.5, border: '1px solid #eee', borderRadius: 2, bgcolor: '#FFFDE7' }}>
                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                  <Chip size="small" color="warning" label={CONFLICT_FA[c.conflict_type] ?? c.conflict_type} sx={{ fontWeight: 800 }} />
                  <Typography variant="caption">ردیف {c.row_number ?? '—'} | {c.source_system ?? '—'} : {c.external_vehicle_id ?? '—'}</Typography>
                  <Box sx={{ flex: 1 }} />
                  <Button size="small" variant="outlined" onClick={() => { setResolveId(c.id); setResolveAction('APPLY'); setResolveNote('') }}>
                    اعمال
                  </Button>
                  <Button size="small" color="inherit" onClick={() => { setResolveId(c.id); setResolveAction('SKIP'); setResolveNote('') }}>
                    رد با یادداشت
                  </Button>
                </Stack>
                <Typography variant="caption" color="text.secondary" component="div" mt={0.5}>
                  {c.message}
                </Typography>
                {c.incoming && (
                  <Box component="pre" sx={{ mt: 0.5, p: 0.5, bgcolor: '#0d1b2a', color: '#c9d6e3', borderRadius: 1, fontSize: 10, overflow: 'auto', maxHeight: 120, direction: 'ltr' }}>
                    {JSON.stringify(c.incoming, null, 1)}
                  </Box>
                )}
              </Box>
            ))}
          </Stack>
        </CardContent>
      </Card>

      {/* تاریخچهٔ اجراها */}
      <Card variant="outlined" sx={{ borderRadius: 3 }}>
        <CardContent>
          <Typography fontWeight={900} mb={1}>تاریخچهٔ اجراها</Typography>
          {(runs?.items ?? []).length === 0 && <Typography color="text.secondary" variant="body2">هنوز اجرایی ثبت نشده.</Typography>}
          <Stack spacing={1}>
            {(runs?.items ?? []).map((r) => (
              <Stack key={r.id} direction="row" spacing={1} alignItems="center" flexWrap="wrap"
                sx={{ p: 1, border: '1px solid #eee', borderRadius: 2 }}>
                <Chip size="small"
                  label={STATUS_FA[r.status] ?? r.status}
                  color={r.status === 'FAILED' ? 'error' : r.status === 'SUCCESS' ? 'success' : 'warning'} />
                <Chip size="small" variant="outlined" label={r.trigger === 'SCHEDULED' ? 'زمان‌بندی ۰۳:۰۰' : 'دستی'} />
                <Typography variant="caption">
                  {r.started_at ? new Date(r.started_at).toLocaleString('fa-IR') : '—'}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  کل: {r.rows_total} | ساخته: {r.rows_created} | به‌روز: {r.rows_updated} | رد: {r.rows_skipped} | تعارض: {r.conflicts_count}
                </Typography>
                {r.error && <Typography variant="caption" color="error">⚠ {r.error}</Typography>}
              </Stack>
            ))}
          </Stack>
        </CardContent>
      </Card>

      {/* دیالوگ تعیین تکلیف تعارض */}
      <Dialog open={resolveId !== null} onClose={() => setResolveId(null)} maxWidth="sm" fullWidth>
        <DialogTitle>تعیین تکلیف تعارض ({resolveAction === 'APPLY' ? 'اعمال ردیف' : 'رد با یادداشت'})</DialogTitle>
        <DialogContent>
          <TextField
            select fullWidth margin="dense" label="عملیات"
            value={resolveAction}
            onChange={(e) => setResolveAction(e.target.value)}
          >
            <MenuItem value="APPLY">اعمال ردیف (ساخت/به‌روزرسانی خودرو)</MenuItem>
            <MenuItem value="SKIP">رد کردن (بدون تغییر)</MenuItem>
          </TextField>
          <TextField
            fullWidth margin="dense" multiline rows={2} label="یادداشت تصمیم"
            value={resolveNote} onChange={(e) => setResolveNote(e.target.value)}
          />
          <Typography variant="caption" color="text.secondary">
            تصمیم شما با نام کاربری و زمان در گزارش انطباق ثبت می‌شود.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setResolveId(null)}>انصراف</Button>
          <Button variant="contained" disabled={resolve.isPending} onClick={() => resolve.mutate()}>
            ثبت تصمیم
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
