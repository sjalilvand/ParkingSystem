import { useEffect, useState, type FormEvent } from 'react'
import {
  Alert, Box, Button, Card, CardContent, Chip, List, ListItem, ListItemText,
  Stack, TextField, Typography,
} from '@mui/material'
import {
  CameraAlt, Login as EntryIcon, Logout as ExitIcon, Payments,
  Person, PersonOff,
} from '@mui/icons-material'
import { api, apiErrorFa } from '../api/client'
import { useLiveEvents } from '../api/ws'
import { decisionColors, decisionFa, reasonFa } from '../app/theme'
import PlateBox from '../components/PlateBox'
import { parsePlateRaw } from '../components/PlateInput'
import { durationFa, faDate, money } from '../utils/format'

const GATE_API_KEY = 'gate-dev-key'

const eventFa: Record<string, string> = {
  'plate.detected': 'پلاک شناسایی شد',
  'access.allowed': 'تردد مجاز',
  'access.denied': 'تردد ممنوع',
  'barrier.open_request': 'فرمان بازکردن راهبند',
  'barrier.result': 'نتیجه راهبند',
  'notification.new': 'اعلان جدید',
  'session.opened': 'جلسه پارکینگ باز شد',
  'session.closed': 'جلسه پارکینگ بسته شد',
}

interface LookupInfo {
  kind: 'RESIDENT' | 'GUEST'
  owner_name?: string | null
  unit_number?: string | null
  tower_name?: string | null
  plate_province?: string | null
  plate_city?: string | null
  province?: string | null
  city?: string | null
  vehicle?: { id: string; brand?: string | null; model?: string | null; color?: string | null; is_active?: boolean | null } | null
}

interface DecisionResult {
  access_event_id: string
  decision: string
  decision_reason: string
  barrier_action: string
  warnings?: string[]
  unit?: { tower?: string; unit_number?: string } | null
  parking?: { code?: string; zone?: string } | null
  duplicate?: boolean
  session?: {
    duration_seconds?: number
    base_amount?: number
    final_amount?: number
    payment_status?: string
  } | null
}

function IdentityStrip({ info }: { info: LookupInfo | null }) {
  if (!info) return null
  if (info.kind === 'RESIDENT') {
    return (
      <Box sx={{ bgcolor: '#E8F5E9', border: '1px solid #A5D6A7', borderRadius: 2.5, p: 1.25, my: 1.5 }}>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
          <Chip size="small" color="success" icon={<Person />} label="ساکن" />
          {info.owner_name && <Typography variant="body2" fontWeight={800}>{info.owner_name}</Typography>}
          {info.unit_number && (
            <Chip size="small" variant="outlined"
              label={`واحد ${info.unit_number}${info.tower_name ? ` — ${info.tower_name}` : ''}`} />
          )}
          {info.vehicle?.brand && <Chip size="small" variant="outlined" label={String(info.vehicle.brand)} />}
          {info.vehicle?.is_active === false && <Chip size="small" color="error" label="خودرو غیرفعال" />}
        </Stack>
        {info.plate_province && (
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
            {'\u{1F4CD}'} {info.plate_province}{info.plate_city ? ` — ${info.plate_city}` : ''}
          </Typography>
        )}
      </Box>
    )
  }
  return (
    <Box sx={{ bgcolor: '#FFF3E0', border: '1px solid #FFB74D', borderRadius: 2.5, p: 1.25, my: 1.5 }}>
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <Chip size="small" color="warning" icon={<PersonOff />} label="مهمان / ناشناس" />
        {info.province ? (
          <Typography variant="body2" fontWeight={800}>
            {'\u{1F4CD}'} استان: {info.province}{info.city ? ` — شهرستان: ${info.city}` : ''}
          </Typography>
        ) : (
          <Typography variant="body2" color="text.secondary">خودرو در سیستم ثبت نشده است</Typography>
        )}
      </Stack>
    </Box>
  )
}

function GateSide({ direction }: { direction: 'IN' | 'OUT' }) {
  const isEntry = direction === 'IN'
  const [plate, setPlate] = useState('۱۲ ب ۳۴۵ ایران ۶۷')
  const [lookup, setLookup] = useState<LookupInfo | null>(null)
  const [result, setResult] = useState<DecisionResult | null>(null)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [paid, setPaid] = useState(false)

  const gateCode = isEntry ? 'GATE-IN-01' : 'GATE-OUT-01'
  const accent = isEntry ? '#2E7D32' : '#C62828'

  // تشخیص زنده ساکن/مهمان هنگام تایپ پلاک
  useEffect(() => {
    const t = setTimeout(async () => {
      const raw = plate.trim()
      if (!raw) { setLookup(null); return }
      const p = parsePlateRaw(raw)
      const code = p.province || p.two || ''
      try {
        const r = await api.post('/vehicles/plate-lookup', {
          plate_raw: raw,
          code: code || undefined,
          letter: p.letterFa || undefined,
        })
        setLookup(r.data)
      } catch {
        try {
          const regs = await api.get('/base-data/plate-regions')
          const normL = (s: string) => s.replace(/ـ/g, '').replace(/ك/g, 'ک').replace(/[يى]/g, 'ی').trim()
          const rows = ((regs.data ?? []) as { plate_code: string; province: string; city: string; letters?: string | null }[])
            .filter((x) => x.plate_code === code)
          const hit = rows.find((x) => (x.letters || '').split(/\s+/).map(normL).includes(normL(p.letterFa || '')))
          setLookup({ kind: 'GUEST', province: hit?.province ?? rows[0]?.province ?? null, city: hit?.city ?? null })
        } catch { setLookup(null) }
      }
    }, 500)
    return () => clearTimeout(t)
  }, [plate])

  const send = async (e: FormEvent) => {
    e.preventDefault()
    setError(''); setMsg(''); setResult(null); setPaid(false); setBusy(true)
    try {
      const r = await api.post('/gate/events/plate-detected', {
        gate_code: gateCode, direction, plate_raw: plate,
        source_event_id: crypto.randomUUID(), confidence: 97.5,
      }, { headers: { 'X-API-Key': GATE_API_KEY } })
      setResult(r.data)
    } catch (err) {
      setError(apiErrorFa(err))
    } finally { setBusy(false) }
  }

  const openBarrier = async () => {
    if (!result) return
    setBusy(true)
    try {
      await api.post('/gate/barrier/open', {
        gate_code: gateCode, access_event_id: result.access_event_id, reason: 'OPERATOR_PANEL_OPEN',
      })
      setMsg('فرمان بازشدن راهبند ثبت و ارسال شد ✔')
    } catch (err) { setError(apiErrorFa(err)) } finally { setBusy(false) }
  }

  const payNow = async () => {
    if (!result?.session?.final_amount) return
    setBusy(true)
    try {
      const r = await api.post('/payments', {
        plate_raw: plate, amount: result.session.final_amount, reference_number: `GATE-${Date.now()}`,
      })
      setPaid(true)
      setMsg(`پرداخت ثبت شد — رسید ${r.data.reference_number}`)
    } catch (err) { setError(apiErrorFa(err)) } finally { setBusy(false) }
  }

  const color = result ? (decisionColors[result.decision] ?? '#757575') : accent

  return (
    <Card sx={{ borderTop: `6px solid ${color}` }}>
      <CardContent sx={{ p: 2.5 }}>
        <Stack direction="row" spacing={1} alignItems="center" mb={2}>
          {isEntry ? <EntryIcon color="success" /> : <ExitIcon color="error" />}
          <Typography variant="h6" fontWeight={900}>{isEntry ? 'گیت ورود' : 'گیت خروج'}</Typography>
          <Chip size="small" label={gateCode} variant="outlined" />
        </Stack>

        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        {msg && <Alert severity="success" sx={{ mb: 2 }}>{msg}</Alert>}

        <form onSubmit={send}>
          <TextField fullWidth size="small" label="پلاک خودرو (ورودی دوربین)" value={plate}
            onChange={(e) => setPlate(e.target.value)} sx={{ mb: 1.5 }} />
          <Stack alignItems="center" mb={1}><PlateBox plate={plate} /></Stack>
          <IdentityStrip info={lookup} />
          <Button fullWidth variant="contained" color={isEntry ? 'primary' : 'secondary'}
            startIcon={<CameraAlt />} type="submit" disabled={busy} sx={{ mt: 1.5, py: 1.2 }}>
            ارسال رویداد دوربین
          </Button>
        </form>

        {result && (
          <Box sx={{ mt: 2, bgcolor: color, borderRadius: 3, p: 2, color: '#fff' }}>
            <Stack alignItems="center" mb={1}><PlateBox plate={plate} size="lg" /></Stack>
            <Typography variant="h4" fontWeight={900} textAlign="center" mb={0.5}>
              {decisionFa[result.decision] ?? result.decision}
            </Typography>
            <Stack direction="row" spacing={1} justifyContent="center" mb={1} flexWrap="wrap" useFlexGap>
              <Chip size="small" label={`راهبند: ${result.barrier_action === 'OPEN' ? 'باز شود' : 'بسته'}`}
                sx={{ bgcolor: 'rgba(255,255,255,.25)', color: '#fff', fontWeight: 700 }} />
              {result.duplicate && <Chip size="small" label="تکراری" sx={{ bgcolor: 'rgba(255,255,255,.25)', color: '#fff' }} />}
            </Stack>
            <Typography variant="body2" textAlign="center">دلیل: {reasonFa[result.decision_reason] ?? result.decision_reason}</Typography>
            {result.unit && <Typography variant="body2" textAlign="center">واحد: {result.unit.tower} — {result.unit.unit_number}</Typography>}
            {result.parking?.code && <Typography variant="body2" textAlign="center">پارکینگ: {result.parking.code}</Typography>}

            {result.session && (
              <Box sx={{ bgcolor: 'rgba(0,0,0,.22)', borderRadius: 2.5, p: 1.5, mt: 1.5, textAlign: 'center' }}>
                <Typography variant="subtitle2" fontWeight={800}>صورتحساب توقف</Typography>
                <Typography variant="body2">مدت: {durationFa(result.session.duration_seconds)}</Typography>
                <Typography variant="h5" fontWeight={900}>{money(result.session.final_amount)}</Typography>
                <Typography variant="caption">
                  {result.session.payment_status === 'UNPAID' ? 'پرداخت‌نشده' : result.session.payment_status}
                </Typography>
              </Box>
            )}
            {result.warnings && result.warnings.length > 0 && (
              <Alert severity="warning" sx={{ mt: 1, bgcolor: '#fff' }}>{result.warnings.join('، ')}</Alert>
            )}
            <Stack spacing={1} mt={1.5}>
              {result.barrier_action === 'OPEN' && (
                <Button fullWidth variant="contained" sx={{ bgcolor: '#fff', color, py: 1.2 }}
                  onClick={openBarrier} disabled={busy}>
                  تأیید و بازکردن راهبند
                </Button>
              )}
              {result.session && result.session.payment_status === 'UNPAID' && (result.session.final_amount ?? 0) > 0 && !paid && (
                <Button fullWidth variant="contained" color="warning" startIcon={<Payments />} onClick={payNow} disabled={busy}>
                  ثبت پرداخت {money(result.session.final_amount)}
                </Button>
              )}
              {paid && <Alert severity="success" sx={{ bgcolor: '#fff' }}>پرداخت انجام شد ✔</Alert>}
            </Stack>
          </Box>
        )}
      </CardContent>
    </Card>
  )
}

export default function GatePanel() {
  const { events, connected } = useLiveEvents(15)
  return (
    <Stack spacing={2}>
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: '1fr 1fr' }, gap: 2 }}>
        <GateSide direction="IN" />
        <GateSide direction="OUT" />
      </Box>
      <Card>
        <CardContent sx={{ py: 2 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center">
            <Typography variant="body2" color="text.secondary">رویدادهای زنده</Typography>
            <Chip size="small" label={connected ? 'WebSocket متصل' : 'قطع'} color={connected ? 'success' : 'default'} />
          </Stack>
          <List dense sx={{ maxHeight: 200, overflow: 'auto' }}>
            {events.map((e) => (
              <ListItem key={e.event_id} divider>
                <ListItemText
                  primary={`${eventFa[e.event] ?? e.event} — ${String((e.data as { plate?: string })?.plate ?? (e.data as { title?: string })?.title ?? '')}`}
                  secondary={faDate(e.occurred_at)}
                />
              </ListItem>
            ))}
          </List>
        </CardContent>
      </Card>
    </Stack>
  )
}