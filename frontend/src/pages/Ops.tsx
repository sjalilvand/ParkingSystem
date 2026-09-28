import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, Box, Button, Card, CardContent, Chip, MenuItem, Stack, TextField, Typography,
} from '@mui/material'
import { Refresh } from '@mui/icons-material'
import { api, apiErrorFa } from '../api/client'
import { decisionFa } from '../app/theme'
import { faDate } from '../utils/format'
import PlateBox from '../components/PlateBox'

interface GateRow { code: string; name: string; direction: string; online: boolean }
interface StatusData { gates: GateRow[]; devices: number
  events_last_hour: { total: number; by_decision: Record<string, number> } }
interface LogData { name: string; exists: boolean; lines: string[] }
interface CfgItem { key: string; value: string; writable: boolean }
interface SimStatus { running: boolean; entry: number; exit: number; violations: number
  resident_entries: number; guest_entries: number; inside_count: number
  max_stay_seconds: number; provinces_total: number; by_province: Record<string, number> }
interface FineRow { [k: string]: unknown }

const LOG_NAMES = ['vision', 'backend', 'frontend', 'agent', 'autostart', 'anpr']
const dur = (s?: number) => {
  if (!s || s <= 0) return '-'
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60)
  return h > 0 ? `${h} ساعت و ${m} دقیقه` : `${m} دقیقه`
}

export default function Ops() {
  const qc = useQueryClient()
  const [logName, setLogName] = useState('vision')
  const [cfg, setCfg] = useState<Record<string, string>>({})
  const [fineForm, setFineForm] = useState({ plate: '', amount: '500000', reason: '', vtype: 'MANUAL' })
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const { data: status } = useQuery({
    queryKey: ['ops-status'],
    queryFn: async () => (await api.get('/ops/status')).data as StatusData,
    refetchInterval: 10000,
  })
  const { data: sim } = useQuery({
    queryKey: ['ops-sim'],
    queryFn: async () => (await api.get('/simulator/status')).data as SimStatus,
    refetchInterval: 3000,
  })
  const { data: fines } = useQuery({
    queryKey: ['ops-fines'],
    queryFn: async () => (await api.get('/ops/fines')).data as { items: FineRow[] },
    refetchInterval: 6000,
  })
  const { data: log } = useQuery({
    queryKey: ['ops-log', logName],
    queryFn: async () => (await api.get('/ops/logs', { params: { name: logName, lines: 200 } })).data as LogData,
    refetchInterval: 5000,
  })
  const { data: cfgData } = useQuery({
    queryKey: ['ops-config'],
    queryFn: async () => (await api.get('/ops/config')).data as { items: CfgItem[]; env_path: string },
  })

  const saveConfig = async () => {
    setErr(''); setMsg('')
    if (!Object.keys(cfg).length) { setMsg('تغییری وارد نشده است'); return }
    try {
      const r = await api.post('/ops/config', { updates: cfg })
      setMsg('ذخیره شد: ' + ((r.data.changed ?? []) as string[]).join('، '))
      setCfg({}); qc.invalidateQueries({ queryKey: ['ops-config'] })
    } catch (e) { setErr(apiErrorFa(e)) }
  }

  const issueFine = async () => {
    setErr(''); setMsg('')
    if (!fineForm.plate.trim()) { setErr('پلاک را وارد کنید'); return }
    try {
      const r = await api.post('/ops/fine', {
        plate_raw: fineForm.plate, amount: parseInt(fineForm.amount) || 500000,
        reason: fineForm.reason || null, violation_type: fineForm.vtype,
      })
      setMsg(`جریمه ثبت شد — ${r.data.plate} مبلغ ${r.data.amount} ریال`)
      setFineForm({ plate: '', amount: '500000', reason: '', vtype: 'MANUAL' })
      qc.invalidateQueries({ queryKey: ['ops-fines'] })
    } catch (e) { setErr(apiErrorFa(e)) }
  }

  return (
    <Stack spacing={2}>
      <Typography variant="h6" fontWeight={800}>مرکز عملیات</Typography>
      {err && <Alert severity="error">{err}</Alert>}
      {msg && <Alert severity="success">{msg}</Alert>}

      <Card><CardContent>
        <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1.5}>
          <Typography fontWeight={800}>گیت‌ها و دستگاه‌ها</Typography>
          <Chip size="small" label={`دستگاه‌ها: ${status?.devices ?? '-'}`} variant="outlined" />
        </Stack>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          {(status?.gates ?? []).map((g) => (
            <Box key={g.code} sx={{ border: '1px solid #E3EAF2', borderRadius: 2.5, p: 1.5, minWidth: 210 }}>
              <Stack direction="row" spacing={1} alignItems="center">
                <Chip size="small" label={g.online ? 'آنلاین' : 'آفلاین'} color={g.online ? 'success' : 'default'} />
                <Typography fontWeight={800}>{g.name}</Typography>
              </Stack>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                {g.code} — جهت: {g.direction === 'IN' ? 'ورود' : 'خروج'}
              </Typography>
            </Box>
          ))}
        </Stack>
      </CardContent></Card>

      <Card><CardContent>
        <Typography fontWeight={800} mb={1.5}>📊 آمار زنده تردد</Typography>
        <Stack direction="row" spacing={1.2} flexWrap="wrap" useFlexGap alignItems="center">
          <Chip color={sim?.running ? 'success' : 'default'} label={sim?.running ? 'شبیه‌ساز فعال' : 'شبیه‌ساز متوقف'} />
          <Chip label={`ورود: ${sim?.entry ?? 0}`} color="primary" variant="outlined" />
          <Chip label={`خروج: ${sim?.exit ?? 0}`} color="secondary" variant="outlined" />
          <Chip label={`ورود ساکن: ${sim?.resident_entries ?? 0}`} color="success" variant="outlined" />
          <Chip label={`ورود مهمان: ${sim?.guest_entries ?? 0}`} color="warning" variant="outlined" />
          <Chip label={`ممنوع/جریمه: ${sim?.violations ?? 0}`} color="error" variant="outlined" />
          <Chip label={`🚗 داخل مجموعه: ${sim?.inside_count ?? 0}`} color="info" variant="outlined" />
          <Chip label={`⏱ بیشترین توقف: ${dur(sim?.max_stay_seconds)}`} color="primary" variant="outlined" />
        </Stack>
        {Object.keys(sim?.by_province ?? {}).length > 0 && (
          <>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1.5, mb: 0.5 }}>
              🗺 ورود به تفکیک استان ({sim?.provinces_total ?? 0} استان):
            </Typography>
            <Stack direction="row" spacing={0.8} flexWrap="wrap" useFlexGap>
              {Object.entries(sim?.by_province ?? {}).map(([p, n]) => (
                <Chip key={p} size="small" label={`📍 ${p}: ${n}`} variant="outlined" />
              ))}
            </Stack>
          </>
        )}
      </CardContent></Card>

      <Card><CardContent>
        <Typography fontWeight={800} mb={1.5}>💰 صدور و گزارش جریمه‌ها</Typography>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} alignItems={{ sm: 'center' }} flexWrap="wrap" useFlexGap>
          <TextField size="small" label="پلاک" value={fineForm.plate}
            onChange={(e) => setFineForm((f) => ({ ...f, plate: e.target.value }))} sx={{ minWidth: 220 }} />
          <TextField size="small" select label="نوع تخلف" value={fineForm.vtype}
            onChange={(e) => setFineForm((f) => ({ ...f, vtype: e.target.value }))} sx={{ minWidth: 140 }}>
            <MenuItem value="MANUAL">تخلف دستی</MenuItem>
            <MenuItem value="UNKNOWN_PLATE">پلاک ناشناس</MenuItem>
            <MenuItem value="BANNED">خودرو ممنوع</MenuItem>
            <MenuItem value="PARKING">تخلف پارکینگ</MenuItem>
          </TextField>
          <TextField size="small" label="مبلغ (ریال)" value={fineForm.amount}
            onChange={(e) => setFineForm((f) => ({ ...f, amount: e.target.value.replace(/\D/g, '') }))} sx={{ width: 130 }} />
          <TextField size="small" label="دلیل" value={fineForm.reason}
            onChange={(e) => setFineForm((f) => ({ ...f, reason: e.target.value }))} sx={{ minWidth: 160 }} />
          <Button variant="contained" color="error" onClick={issueFine}>صدور جریمه</Button>
        </Stack>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1.5, mb: 1 }}>جریمه‌های اخیر:</Typography>
        <Stack spacing={1}>
          {(fines?.items ?? []).map((r, i) => {
            const plate = String(r.plate_normalized ?? r.plate_raw ?? '-')
            const amount = Number(r.amount ?? r.fine_amount ?? 0)
            const reason = String(r.reason ?? r.description ?? r.violation_type ?? r.type ?? '')
            return (
              <Stack key={String(r.id ?? i)} direction={{ xs: 'column', sm: 'row' }} spacing={1.2}
                alignItems={{ sm: 'center' }} sx={{ border: '1px solid #E3EAF2', borderRadius: 2.5, p: 1 }}>
                <PlateBox plate={plate} size="sm" />
                <Chip size="small" color="error" label={`${amount.toLocaleString('fa-IR')} ریال`} />
                <Typography variant="caption" sx={{ flex: 1 }}>{reason || '-'}</Typography>
                <Typography variant="caption" color="text.secondary">{faDate(String(r.created_at ?? ''))}</Typography>
              </Stack>
            )
          })}
          {(fines?.items ?? []).length === 0 && <Typography color="text.secondary">جریمه‌ای ثبت نشده است.</Typography>}
        </Stack>
      </CardContent></Card>

      <Card><CardContent>
        <Stack direction="row" spacing={1.5} alignItems="center" mb={1.5}>
          <Typography fontWeight={800}>لاگ زنده</Typography>
          <TextField size="small" select value={logName} onChange={(e) => setLogName(e.target.value)} sx={{ minWidth: 160 }}>
            {LOG_NAMES.map((n) => <MenuItem key={n} value={n}>{n}.log</MenuItem>)}
          </TextField>
          <Button size="small" startIcon={<Refresh />}
            onClick={() => qc.invalidateQueries({ queryKey: ['ops-log', logName] })}>به‌روزرسانی</Button>
        </Stack>
        <Box component="pre" sx={{
          bgcolor: '#102027', color: '#B2EBF2', p: 2, borderRadius: 2.5, m: 0,
          maxHeight: 300, overflow: 'auto', fontSize: 12.5, direction: 'ltr', textAlign: 'left',
        }}>
          {(log?.lines ?? []).join('\n') || (log?.exists === false ? '(فایل لاگ هنوز ساخته نشده)' : '...')}
        </Box>
      </CardContent></Card>

      <Card><CardContent>
        <Typography fontWeight={800} mb={0.5}>تنظیمات دوربین و Vision</Typography>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1.5 }}>
          فایل: {cfgData?.env_path} — پس از ذخیره، پروسه‌های مربوطه را ری‌استارت کنید
        </Typography>
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 1.5 }}>
          {(cfgData?.items ?? []).map((it) => (
            <TextField key={it.key} size="small" label={it.key + (it.writable ? '' : ' (فقط نمایش)')}
              value={cfg[it.key] ?? it.value} disabled={!it.writable}
              onChange={(e) => setCfg((c) => ({ ...c, [it.key]: e.target.value }))} />
          ))}
        </Box>
        <Button variant="contained" sx={{ mt: 1.5 }} onClick={saveConfig}>ذخیره تنظیمات</Button>
      </CardContent></Card>
    </Stack>
  )
}