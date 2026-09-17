import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, Box, Button, Card, CardContent, Chip, MenuItem, Stack, TextField, Typography,
} from '@mui/material'
import { Refresh } from '@mui/icons-material'
import { api, apiErrorFa } from '../api/client'
import { decisionFa } from '../app/theme'

interface GateRow { code: string; name: string; direction: string; status: string; last_seen_at?: string | null; online: boolean }
interface StatusData { server_time: string; gates: GateRow[]; devices: number; events_last_hour: { total: number; by_decision: Record<string, number> } }
interface LogData { name: string; exists: boolean; lines: string[] }
interface CfgItem { key: string; value: string; writable: boolean }

const LOG_NAMES = ['vision', 'backend', 'frontend', 'agent', 'autostart']

export default function Ops() {
  const qc = useQueryClient()
  const [logName, setLogName] = useState('vision')
  const [cfg, setCfg] = useState<Record<string, string>>({})
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const { data: status } = useQuery({
    queryKey: ['ops-status'],
    queryFn: async () => (await api.get('/ops/status')).data as StatusData,
    refetchInterval: 10000,
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
      setCfg({})
      qc.invalidateQueries({ queryKey: ['ops-config'] })
    } catch (e) { setErr(apiErrorFa(e)) }
  }

  return (
    <Stack spacing={2}>
      <Typography variant="h6" fontWeight={800}>مرکز عملیات</Typography>
      {err && <Alert severity="error">{err}</Alert>}
      {msg && <Alert severity="success">{msg}</Alert>}

      {/* --- وضعیت گیت‌ها --- */}
      <Card>
        <CardContent>
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
            {!status?.gates?.length && <Typography color="text.secondary">گیتی ثبت نشده است</Typography>}
          </Stack>
        </CardContent>
      </Card>

      {/* --- شناسایی‌های یک ساعت اخیر --- */}
      <Card>
        <CardContent>
          <Typography fontWeight={800} mb={1.5}>شناسایی‌های یک ساعت اخیر</Typography>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
            <Chip label={`کل: ${status?.events_last_hour?.total ?? 0}`} color="primary" />
            {Object.entries(status?.events_last_hour?.by_decision ?? {}).map(([d, n]) => (
              <Chip key={d} variant="outlined" label={`${decisionFa[d] ?? d}: ${n}`} />
            ))}
          </Stack>
        </CardContent>
      </Card>

      {/* --- لاگ زنده --- */}
      <Card>
        <CardContent>
          <Stack direction="row" spacing={1.5} alignItems="center" mb={1.5}>
            <Typography fontWeight={800}>لاگ زنده</Typography>
            <TextField size="small" select value={logName} onChange={(e) => setLogName(e.target.value)}
              sx={{ minWidth: 160 }}>
              {LOG_NAMES.map((n) => <MenuItem key={n} value={n}>{n}.log</MenuItem>)}
            </TextField>
            <Button size="small" startIcon={<Refresh />}
              onClick={() => qc.invalidateQueries({ queryKey: ['ops-log', logName] })}>به‌روزرسانی</Button>
          </Stack>
          <Box component="pre" sx={{
            bgcolor: '#102027', color: '#B2EBF2', p: 2, borderRadius: 2.5, m: 0,
            maxHeight: 320, overflow: 'auto', fontSize: 12.5, direction: 'ltr', textAlign: 'left',
          }}>
            {(log?.lines ?? []).join('\n') || (log?.exists === false ? '(فایل لاگ هنوز ساخته نشده)' : '...')}
          </Box>
        </CardContent>
      </Card>

      {/* --- تنظیمات دوربین --- */}
      <Card>
        <CardContent>
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
        </CardContent>
      </Card>
    </Stack>
  )
}