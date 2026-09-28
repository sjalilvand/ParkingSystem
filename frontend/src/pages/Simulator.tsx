import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, Box, Button, Card, CardContent, Chip, MenuItem, Stack, TextField, Typography,
} from '@mui/material'
import { PlayArrow, Stop, TouchApp } from '@mui/icons-material'
import { api, apiErrorFa } from '../api/client'
import { useLiveEvents } from '../api/ws'
import { decisionFa } from '../app/theme'
import PlateBox from '../components/PlateBox'
import { faDate } from '../utils/format'

interface SimEvent { time: string; gate: string; direction: 'IN' | 'OUT'; plate: string
  kind?: string; decision?: string; reason?: string; barrier?: string; inside_count?: number }
interface SimStatus { running: boolean; events: number; entry: number; exit: number
  violations: number; interval: number; resident_ratio: number; inside_count: number }
interface InsideRow { plate: string; kind: string; seconds: number }
interface DurRow { plate: string; seconds: number; to: string; kind: string
  owner?: string | null; unit?: string | null; tower?: string | null
  province?: string | null; city?: string | null }

const dur = (s?: number) => {
  if (!s || s < 0) return '-'
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60)
  return h > 0 ? `${h} ساعت و ${m} دقیقه` : `${m} دقیقه`
}

export default function Simulator() {
  const qc = useQueryClient()
  const [interval, setIntervalS] = useState('4')
  const [ratio, setRatio] = useState('0.8')
  const [err, setErr] = useState('')
  const { events } = useLiveEvents(40)

  const { data: st } = useQuery({
    queryKey: ['sim-status'],
    queryFn: async () => (await api.get('/simulator/status')).data as SimStatus,
    refetchInterval: 3000,
  })
  const { data: inside } = useQuery({
    queryKey: ['sim-inside'],
    queryFn: async () => (await api.get('/simulator/inside')).data as { count: number; items: InsideRow[] },
    refetchInterval: 5000,
  })
  const { data: durs } = useQuery({
    queryKey: ['sim-durations'],
    queryFn: async () => (await api.get('/simulator/durations')).data as { items: DurRow[] },
    refetchInterval: 7000,
  })

  const act = async (path: string, params = '') => {
    setErr('')
    try { await api.post(`/simulator/${path}${params}`); qc.invalidateQueries({ queryKey: ['sim-status'] }) }
    catch (e) { setErr(apiErrorFa(e)) }
  }

  const simEvents = events.filter((e) => e.event === 'simulator.event')
  const colorOf = (d?: string) =>
    d === 'ALLOW' || d === 'ALLOW_WITH_WARNING' ? 'success' : d === 'DENY' ? 'error'
    : d === 'UNKNOWN_PLATE' ? 'warning' : 'default'

  return (
    <Stack spacing={2}>
      <Typography variant="h6" fontWeight={800}>🎮 شبیه‌ساز تردد و جریمه — نسخه کامل</Typography>
      {err && <Alert severity="error">{err}</Alert>}

      <Card><CardContent>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} alignItems={{ sm: 'center' }} flexWrap="wrap" useFlexGap>
          {st?.running ? (
            <Button variant="contained" color="error" startIcon={<Stop />} onClick={() => act('stop')}>توقف</Button>
          ) : (
            <Button variant="contained" color="success" startIcon={<PlayArrow />}
              onClick={() => act('start', `?interval=${interval}&resident_ratio=${ratio}`)}>شروع شبیه‌سازی</Button>
          )}
          <Button variant="outlined" startIcon={<TouchApp />} onClick={() => act('tick')}>یک رویداد دستی</Button>
          <TextField size="small" select label="فاصله (ثانیه)" value={interval}
            onChange={(e) => setIntervalS(e.target.value)} sx={{ width: 150 }}>
            {['2','4','6','10','15'].map((v) => <MenuItem key={v} value={v}>{v}</MenuItem>)}
          </TextField>
          <TextField size="small" select label="نسبت ساکن" value={ratio}
            onChange={(e) => setRatio(e.target.value)} sx={{ width: 150 }}>
            <MenuItem value="0.5">۵۰٪</MenuItem><MenuItem value="0.8">۸۰٪</MenuItem><MenuItem value="0.9">۹۰٪</MenuItem>
          </TextField>
        </Stack>
        <Stack direction="row" spacing={1.2} flexWrap="wrap" useFlexGap mt={2} alignItems="center">
          <Chip color={st?.running ? 'success' : 'default'} label={st?.running ? 'در حال اجرا' : 'متوقف'} />
          <Chip variant="outlined" label={`کل: ${st?.events ?? 0}`} />
          <Chip label={`ورود: ${st?.entry ?? 0}`} color="primary" variant="outlined" />
          <Chip label={`خروج: ${st?.exit ?? 0}`} color="secondary" variant="outlined" />
          <Chip label={`ممنوع/جریمه: ${st?.violations ?? 0}`} color="warning" variant="outlined" />
          <Chip label={`🚗 داخل مجموعه: ${st?.inside_count ?? 0}`} color="info" />
        </Stack>
      </CardContent></Card>

      <Card><CardContent>
        <Typography fontWeight={800} mb={1}>🚦 جریان زنده ورود/خروج</Typography>
        {simEvents.length === 0 && <Typography color="text.secondary">شروع کنید...</Typography>}
        <Stack spacing={1}>
          {simEvents.map((e) => {
            const d = e.data as SimEvent
            return (
              <Stack key={e.event_id} direction={{ xs: 'column', sm: 'row' }} spacing={1.2}
                alignItems={{ sm: 'center' }} sx={{ border: '1px solid #E3EAF2', borderRadius: 2.5, p: 1.2 }}>
                <Chip size="small" color={d.direction === 'IN' ? 'primary' : 'secondary'}
                  label={d.direction === 'IN' ? '⬅ ورود' : 'خروج ➡'} sx={{ minWidth: 88 }} />
                <PlateBox plate={d.plate} size="sm" />
                {d.kind && <Chip size="small" variant="outlined" label={d.kind === 'RESIDENT' ? 'ساکن' : 'مهمان'} />}
                <Chip size="small" color={colorOf(d.decision) as never}
                  label={decisionFa[d.decision ?? ''] ?? d.decision ?? '-'} />
                <Typography variant="caption" color="text.secondary" sx={{ flex: 1 }}>
                  {d.gate} — {decisionFa[d.reason ?? ''] ?? d.reason ?? ''}{d.barrier === 'OPEN' ? ' — راهبند باز' : ''}
                  {typeof d.inside_count === 'number' ? ` — داخل: ${d.inside_count}` : ''}
                </Typography>
                <Typography variant="caption" color="text.secondary">{faDate(e.occurred_at)}</Typography>
              </Stack>
            )
          })}
        </Stack>
      </CardContent></Card>

      <Card><CardContent>
        <Typography fontWeight={800} mb={1}>🅿️ خودروهای داخل مجموعه ({inside?.count ?? 0})</Typography>
        <Stack spacing={1}>
          {(inside?.items ?? []).map((r) => (
            <Stack key={r.plate} direction={{ xs: 'column', sm: 'row' }} spacing={1.2} alignItems={{ sm: 'center' }}
              sx={{ border: '1px solid #E3EAF2', borderRadius: 2.5, p: 1 }}>
              <PlateBox plate={r.plate} size="sm" />
              <Chip size="small" variant="outlined" label={r.kind === 'RESIDENT' ? 'ساکن' : 'مهمان'} />
              <Typography variant="caption" sx={{ flex: 1 }}>مدت حضور: {dur(r.seconds)}</Typography>
            </Stack>
          ))}
          {(inside?.items ?? []).length === 0 && <Typography color="text.secondary">مجموعه خالی است.</Typography>}
        </Stack>
      </CardContent></Card>

      <Card><CardContent>
        <Typography fontWeight={800} mb={1}>⏱ گزارش مدت توقف (آخرین خروج‌ها)</Typography>
        <Stack spacing={1}>
          {(durs?.items ?? []).map((r, i) => (
            <Stack key={i} direction={{ xs: 'column', sm: 'row' }} spacing={1.2} alignItems={{ sm: 'center' }}
              sx={{ border: '1px solid #E3EAF2', borderRadius: 2.5, p: 1 }}>
              <PlateBox plate={r.plate} size="sm" />
              <Chip size="small" color={r.kind === 'RESIDENT' ? 'success' : 'warning'}
                label={r.kind === 'RESIDENT' ? 'ساکن' : 'مهمان'} sx={{ minWidth: 74 }} />
              <Typography variant="caption" sx={{ flex: 1 }}>
                {r.kind === 'RESIDENT'
                  ? `${r.owner ?? 'ساکن'}${r.unit ? ` — واحد ${r.unit}` : ''}${r.tower ? ` (${r.tower})` : ''}`
                  : `غریبه — ${r.province ?? '?'}${r.city ? ` / ${r.city}` : ''}`}
              </Typography>
              <Typography variant="body2" fontWeight={800}>مدت توقف: {dur(r.seconds)}</Typography>
              <Typography variant="caption" color="text.secondary">{faDate(r.to)}</Typography>
            </Stack>
          ))}
          {(durs?.items ?? []).length === 0 && <Typography color="text.secondary">هنوز خروجی ثبت نشده.</Typography>}
        </Stack>
      </CardContent></Card>
    </Stack>
  )
}