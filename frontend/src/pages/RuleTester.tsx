import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Alert, Box, Button, Card, CardContent, Chip, MenuItem, Stack, TextField, Typography,
} from '@mui/material'
import { PlayArrow, Science } from '@mui/icons-material'
import { api } from '../api/client'
import JalaliDatePicker from '../components/JalaliDateTime'

interface Cond { field: string; op: string; value?: unknown }
interface Act { action: string; params?: Record<string, unknown> }
interface Trace { rule_id: string; rule_name: string; conditions: Cond[]; condition_results: boolean[]; actions: Act[]; context: Record<string, unknown> }
interface CheckResp {
  decision: string; decision_reason: string; barrier_action: string
  warnings?: string[]; duplicate?: boolean; rule_trace?: Trace | null
  session?: { final_amount?: number; payment_status?: string } | null
  message?: string; require_driver_selection?: boolean
  plate?: { normalized?: string | null }
}

const FIELD_FA: Record<string, string> = {
  membership_kind: 'گروه خودرو', is_resident: 'ساکن است', has_valid_permit: 'حق استفاده معتبر',
  yard_full: 'ظرفیت محوطه پر', covered_free_count: 'جایگاه مسقف آزاد',
  has_open_session: 'جلسه فعال', has_debt: 'بدهی قبلی',
  confirmed_violations_count: 'تخلف تأییدشده', driver_request: 'درخواست راننده',
  time_window: 'بازه زمانی', gate_code: 'کد گیت', plate_in: 'پلاک در فهرست',
}
const OP_FA: Record<string, string> = {
  true: 'برقرار است', false: 'برقرار نیست', eq: '=', ne: '≠', in: 'یکی از',
  not_in: 'هیچ‌کدام از', gte: '≥', lte: '≤', time_window: 'در بازه',
}
const MEM_FA: Record<string, string> = {
  PRIMARY_WITH_COVERED: 'اصلی-مسقف', SECONDARY_WITH_COVERED: 'جایگزین-مسقف',
  RESIDENT_YARD: 'ساکن-محوطه', NONRESIDENT_YARD: 'غیرساکن-محوطه', SPECIAL_PERMIT: 'مجوز ویژه',
}
const ctxFa = (k: string, v: unknown): string => {
  if (k === 'membership_kind') return v ? (MEM_FA[String(v)] ?? String(v)) : 'بدون گروه'
  if (typeof v === 'boolean') return v ? 'بله' : 'خیر'
  return String(v ?? '—')
}
const decisionFa: Record<string, string> = {
  ALLOW: 'اجازه عبور', ALLOW_WITH_WARNING: 'اجازه با هشدار',
  REQUIRE_OPERATOR_APPROVAL: 'نیاز به تأیید اپراتور', DENY: 'رد',
  UNKNOWN_PLATE: 'پلاک ناشناس',
}

export default function RuleTester() {
  const [plate, setPlate] = useState('')
  const [direction, setDirection] = useState<'IN' | 'OUT'>('IN')
  const [gateCode, setGateCode] = useState('GATE-IN-01')
  const [driverReq, setDriverReq] = useState('')
  const [calcIn, setCalcIn] = useState('')
  const [calcOut, setCalcOut] = useState('')
  const [results, setResults] = useState<{ label: string; resp: CheckResp | null; error?: string }[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const { data: vehicles } = useQuery({
    queryKey: ['vt-quick'],
    queryFn: async () => (await api.get('/vehicles', { params: { page_size: 50 } })).data as { items: { plate_raw: string }[] },
  })

  const durationSec = useMemo(() => {
    if (!calcIn || !calcOut) return null
    const a = new Date(calcIn), b = new Date(calcOut)
    if (isNaN(a.getTime()) || isNaN(b.getTime())) return null
    return Math.max(0, Math.round((b.getTime() - a.getTime()) / 1000))
  }, [calcIn, calcOut])

  const check = async (label: string, pl = plate, dir = direction, dreq = driverReq) => {
    const body: Record<string, unknown> = {
      gate_code: dir === 'IN' ? 'GATE-IN-01' : 'GATE-OUT-01',
      direction: dir, plate_raw: pl || (vehicles?.items?.[0]?.plate_raw ?? ''),
      source_event_id: crypto.randomUUID(),
    }
    if (dreq) body.driver_request = dreq
    try {
      const r = await api.post('/gate/access/check', body)
      return { label, resp: r.data as CheckResp }
    } catch (e) {
      return { label, resp: null, error: String((e as { response?: { data?: unknown } })?.response?.data ?? e) }
    }
  }

  const runOne = async () => {
    setBusy(true); setErr(''); setResults([])
    const res = await check('سناریوی انتخابی')
    setResults([res]); setBusy(false)
  }

  const runConcurrent = async () => {
    setBusy(true); setErr(''); setResults([])
    const pair = await Promise.all([
      check('درخواست همزمان #1'),
      check('درخواست همزمان #2'),
    ])
    setResults(pair); setBusy(false)
  }

  const presets: { label: string; apply: () => void }[] = [
    { label: 'ساکن متقاضی محوطه', apply: () => { setDirection('IN'); setDriverReq('YARD') } },
    { label: 'غیرساکن متقاضی محوطه', apply: () => { setDirection('IN'); setDriverReq('YARD') } },
    { label: 'ورود عادی (حق معتبر)', apply: () => { setDirection('IN'); setDriverReq('') } },
    { label: 'خروج بدون ورود ثبت‌شده', apply: () => { setDirection('OUT'); setDriverReq(''); setPlate('99Z999IR11') } },
    { label: 'پلاک ناشناس', apply: () => { setDirection('IN'); setDriverReq(''); setPlate('000X000') } },
  ]

  const stop = (results[0]?.resp ?? null)

  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={1} alignItems="center">
        <Science color="primary" />
        <Typography variant="h6" fontWeight={800}>آزمایش قوانین ورود/خروج (بدون راهبند و پرداخت واقعی)</Typography>
      </Stack>
      {err && <Alert severity="error">{err}</Alert>}

      <Card><CardContent>
        <Typography fontWeight={800} mb={1}>ساخت سناریو</Typography>
        <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap alignItems="center">
          <TextField select size="small" label="جهت" value={direction} sx={{ width: 110 }}
            onChange={(e) => { const d = e.target.value as 'IN' | 'OUT'; setDirection(d); setGateCode(d === 'IN' ? 'GATE-IN-01' : 'GATE-OUT-01') }}>
            <MenuItem value="IN">ورود</MenuItem>
            <MenuItem value="OUT">خروج</MenuItem>
          </TextField>
          <TextField select size="small" label="گیت" value={gateCode} sx={{ width: 170 }}
            onChange={(e) => setGateCode(e.target.value)}>
            <MenuItem value="GATE-IN-01">GATE-IN-01</MenuItem>
            <MenuItem value="GATE-OUT-01">GATE-OUT-01</MenuItem>
          </TextField>
          <TextField size="small" label="پلاک (یا از فهرست)" value={plate} sx={{ width: 200 }}
            onChange={(e) => setPlate(e.target.value)} />
          <TextField select size="small" label="از خودروهای ثبت‌شده" sx={{ width: 210 }} value=""
            onChange={(e) => setPlate(e.target.value)}>
            {(vehicles?.items ?? []).map((v) => <MenuItem key={v.plate_raw} value={v.plate_raw}>{v.plate_raw}</MenuItem>)}
          </TextField>
          <TextField select size="small" label="درخواست راننده" value={driverReq} sx={{ width: 190 }}
            onChange={(e) => setDriverReq(e.target.value)}>
            <MenuItem value="">بدون درخواست</MenuItem>
            <MenuItem value="YARD">پارک در محوطه</MenuItem>
            <MenuItem value="OWN_PARKING">پارکینگ خودم</MenuItem>
          </TextField>
        </Stack>

        {direction === 'OUT' && (
          <Stack direction="row" spacing={1.5} mt={1.5} flexWrap="wrap" useFlexGap alignItems="center">
            <JalaliDatePicker label="ورود فرضی" value={calcIn} onChange={setCalcIn} />
            <JalaliDatePicker label="خروج فرضی" value={calcOut} onChange={setCalcOut} />
            {durationSec !== null && (
              <Chip size="small" label={`مدت فرضی: ${Math.floor(durationSec / 3600)}س ${Math.floor((durationSec % 3600) / 60)}د`} />
            )}
          </Stack>
        )}

        <Stack direction="row" spacing={1} mt={2} flexWrap="wrap" useFlexGap>
          <Button variant="contained" startIcon={<PlayArrow />} disabled={busy} onClick={runOne}>اجرای سناریو (dry-run)</Button>
          <Button variant="outlined" disabled={busy} onClick={runConcurrent}>دو درخواست همزمان</Button>
          {presets.map((p) => (
            <Button key={p.label} size="small" variant="text" onClick={p.apply}>{p.label}</Button>
          ))}
        </Stack>
        <Typography variant="caption" color="text.secondary">
          dry-run هیچ نشست، پرداخت یا بدهی‌ای نمی‌سازد. سناریوی «ظرفیت کامل» نیازمند تنظیم YARD_CAPACITY_TOTAL است.
        </Typography>
      </CardContent></Card>

      {results.map((r) => (
        <Card key={r.label}><CardContent>
          <Typography fontWeight={800} mb={1}>{r.label}</Typography>
          {r.error && <Alert severity="error">{r.error}</Alert>}
          {r.resp && (
            <Stack spacing={1}>
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                <Chip color={r.resp.decision === 'ALLOW' ? 'success' : r.resp.decision === 'ALLOW_WITH_WARNING' ? 'info' : 'error'}
                  label={`تصمیم: ${decisionFa[r.resp.decision] ?? r.resp.decision}`} />
                <Chip variant="outlined" label={`راهبند: ${r.resp.barrier_action === 'OPEN' ? 'باز شود' : 'بسته'}`} />
                <Chip variant="outlined" label={`دلیل: ${r.resp.decision_reason}`} />
                {r.resp.duplicate && <Chip size="small" label="تکراری" />}
              </Stack>
              {r.resp.message && <Alert severity="info" icon={false}>{r.resp.message}</Alert>}
              {r.resp.warnings && r.resp.warnings.length > 0 && (
                <Alert severity="warning">{r.resp.warnings.join('، ')}</Alert>
              )}

              {r.resp.rule_trace ? (
                <Box sx={{ border: '1px solid #E3EAF2', borderRadius: 2, p: 1.5 }}>
                  <Typography fontWeight={800}>قانون اعمال‌شده: {r.resp.rule_trace.rule_name}</Typography>
                  <Typography variant="body2" mt={0.5}>شرایط:</Typography>
                  {r.resp.rule_trace.conditions.map((c, i) => (
                    <Typography key={i} variant="body2" sx={{ pr: 2 }}>
                      {r.resp.rule_trace!.condition_results[i] ? '✅' : '❌'} {FIELD_FA[c.field] ?? c.field} {OP_FA[c.op] ?? c.op}
                      {c.op === 'time_window' ? '' : c.op === 'true' || c.op === 'false' ? '' : ` ${JSON.stringify(c.value ?? '')}`}
                    </Typography>
                  ))}
                  <Typography variant="body2" mt={0.5}>اقدامات: {r.resp.rule_trace.actions.map((a) => a.action).join(' → ')}</Typography>
                  <Typography variant="caption" color="text.secondary" mt={0.5} sx={{ display: 'block' }}>زمینه محاسبه:</Typography>
                  <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                    {Object.entries(r.resp.rule_trace.context).filter(([k]) =>
                      ['membership_kind', 'is_resident', 'has_valid_permit', 'yard_full', 'covered_free_count', 'has_debt', 'debt_amount', 'confirmed_violations_count', 'has_open_session', 'driver_request'].includes(k))
                      .map(([k, v]) => <Chip key={k} size="small" variant="outlined" label={`${FIELD_FA[k] ?? k}: ${ctxFa(k, v)}`} />)}
                  </Stack>
                </Box>
              ) : (
                <Alert severity="info" variant="outlined">قانونی منطبق نشد — مسیر پیش‌فرض ایمن سیستم اجرا شد.</Alert>
              )}

              {direction === 'OUT' && durationSec !== null && (
                <TariffPreview seconds={durationSec} />
              )}
            </Stack>
          )}
        </CardContent></Card>
      ))}
    </Stack>
  )
}

function TariffPreview({ seconds }: { seconds: number }) {
  const [data, setData] = useState<Record<string, unknown> | null>(null)
  const [e, setE] = useState('')
  useMemo(() => {
    api.post('/tariffs/preview', { duration_seconds: seconds })
      .then((r) => setData(r.data)).catch((x) => setE(String(x?.response?.data?.error?.message ?? x)))
  }, [seconds])
  if (e) return <Alert severity="error">{e}</Alert>
  if (!data) return <Typography variant="body2" color="text.secondary">محاسبه تعرفه فرضی…</Typography>
  return (
    <Alert severity="success">
      هزینه فرضی این مدت (بدون ثبت داده): {Number(data.final ?? 0).toLocaleString('fa-IR')} ریال
      {Array.isArray(data.warnings) && (data.warnings as string[]).length > 0 ? ` — ${(data.warnings as string[]).join('، ')}` : ''}
    </Alert>
  )
}
