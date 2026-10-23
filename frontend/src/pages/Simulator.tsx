import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, Box, Button, Card, CardContent, Chip, Divider, FormControlLabel, MenuItem,
  Radio, RadioGroup, Slider, Stack, TextField, Typography,
} from '@mui/material'
import {
  AutoAwesome, PlayArrow, RestartAlt, Stop, TouchApp, MovieFilter,
} from '@mui/icons-material'
import { api, apiErrorFa } from '../api/client'
import { useLiveEvents } from '../api/ws'
import { decisionFa } from '../app/theme'
import PlateBox from '../components/PlateBox'
import { faDate } from '../utils/format'
import SimBanner from '../components/SimBanner'

interface SimEvent { time: string; gate: string; direction: 'IN' | 'OUT'; plate: string
  kind?: string; decision?: string; reason?: string; barrier?: string
  province?: string | null; city?: string | null; inside_count?: number }
interface SimStatus { running: boolean; events: number; entry: number; exit: number
  violations: number; resident_entries: number; guest_entries: number
  max_stay_seconds: number; inside_count: number; provinces_total: number
  by_province: Record<string, number> }
interface InsideRow { plate: string; kind: string; seconds: number; province?: string | null; city?: string | null }
interface DurRow { plate: string; seconds: number; to: string; kind: string
  owner?: string | null; unit?: string | null; tower?: string | null
  province?: string | null; city?: string | null }

interface ScenVehicle { role: string; label: string; plate_raw: string; plate_normalized?: string
  is_active: boolean; has_permit: boolean; space_code?: string | null; space_type?: string | null
  owner?: string }
interface ScenResident { name: string; unit: string; vehicles: ScenVehicle[] }
interface ScenBanned { role: string; label: string; plate_raw: string; restricted: boolean
  restriction_type?: string | null; restriction_reason?: string | null; has_permit: boolean }
interface ScenState {
  residents: ScenResident[]
  strangers: ScenVehicle[]
  banned?: ScenBanned[]
  rules: { code: string; name: string; status: string; enabled: boolean; priority: number }[]
  spaces: { code: string; type: string; status: string }[]
  inside_count: number; occupied_spaces: number; total_spaces: number
  active_rules: number; draft_rules: number; events_total: number
  yard_capacity?: { total: number; source: string } | null
  exit_policy?: string
  tariff_active?: boolean
  phases?: { key: string; title: string }[]
  step_index: number; total_steps: number
}
interface StepResult {
  index?: number; total?: number; title?: string; finished?: boolean; message?: string
  action: 'gate' | 'activate_rule' | 'summary' | 'manual' | 'set_yard_capacity' | 'clear_yard_capacity' | 'set_exit_policy' | 'backdate_session' | 'lift_restriction' | 'grant_permit'
  phase?: string; phase_title?: string
  role?: string | null; role_label?: string; direction?: string; gate_code?: string
  plate_raw?: string; rule_name?: string; rule?: string; error?: string
  policy?: string; hours?: number; minutes?: number; lifted?: number
  result?: {
    decision: string; decision_reason: string; barrier_action: string
    parking?: { code: string; zone?: string } | null
    unit?: { unit_number?: string; tower?: string } | null
    session?: { duration_seconds?: number; final_amount?: number; payment_status?: string } | null
    warnings?: string[]
    rule_trace?: { rule_name?: string } | null
  }
  explanation?: string[]
}

const PHASE_FA: Record<string, { label: string; color: 'primary' | 'warning' | 'secondary' | 'error' | 'success' }> = {
  SETUP: { label: 'محیط‌بندی', color: 'primary' },
  RULES: { label: 'قوانین', color: 'warning' },
  CAPACITY: { label: 'ظرفیت محوطه', color: 'secondary' },
  DEBT: { label: 'خروج با بدهی', color: 'error' },
  RECOVERY: { label: 'جبران/مهمان', color: 'success' },
}

const dur = (s?: number) => {
  if (!s || s <= 0) return '-'
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60)
  return h > 0 ? `${h} ساعت و ${m} دقیقه` : `${m} دقیقه`
}

const colorOf = (d?: string) =>
  d === 'ALLOW' || d === 'ALLOW_WITH_WARNING' ? 'success' : d === 'DENY' ? 'error'
  : d === 'UNKNOWN_PLATE' ? 'warning' : 'info'

export default function Simulator() {
  const qc = useQueryClient()
  const [interval, setIntervalS] = useState('3')
  const [ratio, setRatio] = useState('0.8')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  // سناریو
  const [steps, setSteps] = useState<StepResult[]>([])
  const [manualPlate, setManualPlate] = useState('')
  const [manualDir, setManualDir] = useState('IN')
  const [manualResult, setManualResult] = useState<StepResult | null>(null)
  const { events } = useLiveEvents(40)

  const { data: st } = useQuery({
    queryKey: ['sim-status'],
    queryFn: async () => (await api.get('/simulator/status')).data as SimStatus,
    refetchInterval: 2000,
  })
  const { data: inside } = useQuery({
    queryKey: ['sim-inside'],
    queryFn: async () => (await api.get('/simulator/inside')).data as { count: number; items: InsideRow[] },
    refetchInterval: 4000,
  })
  const { data: durs } = useQuery({
    queryKey: ['sim-durations'],
    queryFn: async () => (await api.get('/simulator/durations')).data as { items: DurRow[] },
    refetchInterval: 6000,
  })
  const { data: scen } = useQuery({
    queryKey: ['scenario-state'],
    queryFn: async () => (await api.get('/simulator/scenario/state')).data as ScenState,
    refetchInterval: 5000,
  })

  const act = async (path: string, params = '') => {
    setErr('')
    try { await api.post(`/simulator/${path}${params}`); qc.invalidateQueries({ queryKey: ['sim-status'] }) }
    catch (e) { setErr(apiErrorFa(e)) }
  }

  const setupScenario = async () => {
    if (!window.confirm('همه داده‌ها (ساکنان، خودروها، رویدادها، قوانین) پاک می‌شود — فقط ادمین و تنظیمات می‌ماند. مطمئنی؟')) return
    setBusy(true); setErr(''); setSteps([]); setManualResult(null)
    try {
      await api.post('/simulator/scenario/setup')
      qc.invalidateQueries({ queryKey: ['scenario-state'] })
      qc.invalidateQueries({ queryKey: ['sim-status'] })
    } catch (e) { setErr(apiErrorFa(e)) } finally { setBusy(false) }
  }
  const nextStep = async () => {
    setBusy(true); setErr('')
    try {
      const r = await api.post('/simulator/scenario/step')
      setSteps((s) => [...s, r.data])
      qc.invalidateQueries({ queryKey: ['scenario-state'] })
    } catch (e) { setErr(apiErrorFa(e)) } finally { setBusy(false) }
  }
  const resetSteps = async () => {
    setSteps([]); setManualResult(null)
    try { await api.post('/simulator/scenario/reset') } catch { /* noop */ }
  }

  const sendManual = async (plate?: string, direction?: string) => {
    const p = (plate ?? manualPlate).trim()
    if (!p) { setErr('پلاک را وارد یا از فهرست انتخاب کن.'); return }
    setBusy(true); setErr('')
    try {
      const r = await api.post('/simulator/scenario/manual', {
        plate_raw: p, direction: direction ?? manualDir,
      })
      setManualResult(r.data)
      qc.invalidateQueries({ queryKey: ['scenario-state'] })
      qc.invalidateQueries({ queryKey: ['sim-status'] })
    } catch (e) { setErr(apiErrorFa(e)) } finally { setBusy(false) }
  }

  const simEvents = events.filter((e) => e.event === 'simulator.event')
  const provs = Object.entries(st?.by_province ?? {})
  const scenVehicles = [...(scen?.residents ?? []).flatMap((r) => r.vehicles.map((v) => ({ ...v, owner: r.name }))),
    ...(scen?.strangers ?? [])]
  const intervalNum = Math.max(1, Math.min(180, Number(interval) || 3))
  const intervalMarks = [1, 15, 30, 60, 120, 180].map((v) => ({ value: v, label: String(v) }))

  const renderStepCard = (s: StepResult, i: number) => (
    <Stack key={i} spacing={0.5} sx={{ border: '1px solid #E3EAF2', borderRadius: 2.5, p: 1.4 }}>
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <Chip size="small" color="primary" sx={{ minWidth: 64 }}
          label={s.index ? `گام ${s.index}` : (s.action === 'manual' ? 'دستی' : 'گام')} />
        <Typography variant="body2" fontWeight={800}>{s.title ?? (s.action === 'manual' ? 'رویداد دستی' : '')}</Typography>
        {s.phase && PHASE_FA[s.phase] && (
          <Chip size="small" color={PHASE_FA[s.phase].color} variant="outlined"
            label={s.phase_title ?? PHASE_FA[s.phase].label} />
        )}
        {s.action === 'gate' && s.direction && (
          <Chip size="small" color={s.direction === 'IN' ? 'primary' : 'secondary'}
            label={s.direction === 'IN' ? '⬅ ورود' : 'خروج ➡'} />
        )}
        {s.action === 'activate_rule' && <Chip size="small" color="warning" label="فعال‌سازی قانون" />}
        {(s.action === 'set_yard_capacity' || s.action === 'clear_yard_capacity' || s.action === 'set_exit_policy') && (
          <Chip size="small" color="secondary" label="تغییر تنظیمات" />
        )}
        {(s.action === 'backdate_session' || s.action === 'lift_restriction' || s.action === 'grant_permit') && (
          <Chip size="small" color="info" label="اقدام اپراتور" />
        )}
        {s.action === 'summary' && <Chip size="small" color="info" label="خلاصه" />}
        {s.plate_raw && s.action === 'gate' && <PlateBox plate={s.plate_raw} size="sm" />}
      </Stack>
      {s.action === 'gate' && s.result && (
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
          <Chip size="small" color={colorOf(s.result.decision) as never}
            label={decisionFa[s.result.decision] ?? s.result.decision} />
          {s.result.barrier_action === 'OPEN'
            ? <Chip size="small" color="success" variant="outlined" label="راهبند: باز" />
            : <Chip size="small" color="default" variant="outlined" label="راهبند: بسته" />}
          {s.result.parking && <Chip size="small" variant="outlined" label={`🅿️ ${s.result.parking.code}`} />}
          {s.result.rule_trace?.rule_name && <Chip size="small" color="warning" label={`قانون: ${s.result.rule_trace.rule_name}`} />}
        </Stack>
      )}
      {s.action === 'activate_rule' && <Chip size="small" color="warning" label={s.rule_name ?? s.rule} />}
      {(s.explanation ?? []).map((x, j) => (
        <Typography key={j} variant="caption" color="text.secondary" sx={{ pr: 1 }}>• {x}</Typography>
      ))}
    </Stack>
  )

  return (
    <Stack spacing={2}>
      <SimBanner />
      <Typography variant="h6" fontWeight={800}>🎮 شبیه‌ساز تردد و جریمه — نسخه کامل</Typography>
      {err && <Alert severity="error">{err}</Alert>}

      {/* ================= سناریوی آزمایشی ================= */}
      <Card><CardContent>
        <Stack direction="row" spacing={1.2} alignItems="center" flexWrap="wrap" useFlexGap>
          <MovieFilter color="primary" />
          <Typography fontWeight={800} sx={{ flex: 1 }}>🎬 سناریوی آزمایشی — محیط‌بندی و گام‌به‌گام</Typography>
          <Chip size="small" variant="outlined" label={`گام: ${scen?.step_index ?? 0}/${scen?.total_steps ?? 32}`} />
          <Chip size="small" color={scen?.active_rules ? 'warning' : 'default'}
            label={`قوانین فعال: ${scen?.active_rules ?? 0} | DRAFT: ${scen?.draft_rules ?? 0}`} />
        </Stack>
        <Typography variant="caption" color="text.secondary" component="div" mt={0.5}>
          پاکسازی کامل (به‌جز ادمین) ← ۲ ساکن (علی رضایی، مریم کریمی) هر کدام یک واحد و ۳ خودرو
          (پارکینگ خودش / متقاضی محوطه / پارکینگ دفنی) + ۲ غریبه فعال بدون مجوز + ۱ خودروی ممنوعه
          + ۳ قانون DRAFT + تعرفه آزمایشی. سپس اجرای گام‌به‌گام در ۵ فاز:
          ۱) تردد پایه ۲) فعال‌سازی قوانین ۳) ظرفیت محوطه پر ۴) خروج با بدهی (D1) ۵) جبران و مهمان.
        </Typography>
        <Stack direction="row" spacing={0.6} mt={1} flexWrap="wrap" useFlexGap>
          {Object.entries(PHASE_FA).map(([k, v]) => (
            <Chip key={k} size="small" variant="outlined" color={v.color} label={v.label} />
          ))}
        </Stack>

        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.2} mt={1.5} alignItems={{ sm: 'center' }} flexWrap="wrap" useFlexGap>
          <Button variant="contained" color="error" startIcon={<RestartAlt />}
            disabled={busy} onClick={setupScenario}>۱) پاکسازی و ساخت سناریو</Button>
          <Button variant="contained" color="primary" startIcon={<PlayArrow />}
            disabled={busy} onClick={nextStep}>۲) گام بعدی</Button>
          <Button variant="outlined" startIcon={<AutoAwesome />}
            disabled={busy} onClick={async () => {
              // اجرای خودکار همه گام‌های باقی‌مانده تا پایان
              setBusy(true)
              try {
                for (let i = 0; i < 20; i++) {
                  const r = await api.post('/simulator/scenario/step')
                  setSteps((s) => [...s, r.data])
                  if (r.data.finished) break
                }
              } catch (e) { setErr(apiErrorFa(e)) } finally { setBusy(false) }
              qc.invalidateQueries({ queryKey: ['scenario-state'] })
            }}>اجرای همه گام‌ها</Button>
          <Button variant="text" startIcon={<Stop />} disabled={busy} onClick={resetSteps}>بازنشانی گام‌ها</Button>
        </Stack>

        {/* وضعیت موجودیت‌های سناریو */}
        {scen && (scen.residents.length > 0 || scen.strangers.length > 0) && (
          <Stack spacing={1} mt={2}>
            {scen.residents.map((r) => (
              <Stack key={r.name} direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'center' }}
                sx={{ border: '1px solid #E3EAF2', borderRadius: 2.5, p: 1 }} flexWrap="wrap" useFlexGap>
                <Chip size="small" color="success" label={`👤 ${r.name} — واحد ${r.unit}`} />
                {r.vehicles.map((v) => (
                  <Stack key={v.role} direction="row" spacing={0.6} alignItems="center">
                    <PlateBox plate={v.plate_raw} size="sm" />
                    <Chip size="small" variant="outlined" sx={{ fontSize: 11 }}
                      label={`${v.label}${v.has_permit ? ' ✓مجوز' : ' ✗مجوز'}${v.space_code ? ` • ${v.space_code}` : ''}`} />
                  </Stack>
                ))}
              </Stack>
            ))}
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
              {scen.strangers.map((v) => (
                <Stack key={v.role} direction="row" spacing={0.6} alignItems="center">
                  <PlateBox plate={v.plate_raw} size="sm" />
                  <Chip size="small" color="error" variant="outlined" sx={{ fontSize: 11 }} label={v.label} />
                </Stack>
              ))}
              {(scen.banned ?? []).map((v) => (
                <Stack key={v.role} direction="row" spacing={0.6} alignItems="center">
                  <PlateBox plate={v.plate_raw} size="sm" />
                  <Chip size="small" color={v.restricted ? 'error' : 'default'}
                    variant={v.restricted ? 'filled' : 'outlined'} sx={{ fontSize: 11 }}
                    label={`${v.label}${v.restricted ? ' (ممنوع)' : ' (ممنوعیت لغو شد)'}`} />
                </Stack>
              ))}
              <Chip size="small" color="info" label={`🚗 داخل: ${scen.inside_count}`} />
              <Chip size="small" variant="outlined" label={`🅿️ اشغال: ${scen.occupied_spaces}/${scen.total_spaces}`} />
            </Stack>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              <Chip size="small" color="secondary" variant="outlined"
                label={`ظرفیت محوطه: ${scen.yard_capacity ? `${scen.yard_capacity.total} (${scen.yard_capacity.source})` : 'نامحدود'}`} />
              <Chip size="small"
                color={scen.exit_policy === 'DENY' ? 'error' : scen.exit_policy === 'ALLOW' ? 'success' : 'warning'}
                variant="outlined" label={`سیاست خروج با بدهی (D1): ${scen.exit_policy ?? 'WARN'}`} />
              <Chip size="small" color={scen.tariff_active ? 'success' : 'default'} variant="outlined"
                label={scen.tariff_active ? 'تعرفه فعال ✓' : 'بدون تعرفه فعال'} />
              {scen.rules.map((r) => (
                <Chip key={r.code} size="small" sx={{ fontSize: 11 }}
                  color={r.status === 'ACTIVE' ? 'warning' : 'default'}
                  variant={r.status === 'ACTIVE' ? 'filled' : 'outlined'}
                  label={`${r.name} — ${r.status === 'ACTIVE' ? 'فعال' : 'DRAFT'}`} />
              ))}
            </Stack>
          </Stack>
        )}

        {/* رویداد دستی — کشویی یا تایپی */}
        {scenVehicles.length > 0 && (
          <Box mt={2} sx={{ borderTop: '1px dashed #E3EAF2', pt: 1.5 }}>
            <Typography fontWeight={800} mb={1}>🖐 رویداد دستی — انتخابی (کشویی) یا تایپِ آزادِ پلاک</Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.2} alignItems={{ sm: 'center' }} flexWrap="wrap" useFlexGap>
              <TextField size="small" select sx={{ minWidth: 280 }}
                label="انتخاب از خودروهای سناریو"
                value={scenVehicles.some((v) => v.plate_raw === manualPlate) ? manualPlate : ''}
                onChange={(e) => setManualPlate(e.target.value)}>
                {scenVehicles.map((v) => (
                  <MenuItem key={v.role} value={v.plate_raw}>
                    {v.label} — {v.plate_raw}{v.owner ? ` (${v.owner})` : ''}
                  </MenuItem>
                ))}
              </TextField>
              <TextField size="small" sx={{ minWidth: 210 }} label="یا تایپ دستی پلاک"
                placeholder="مثلاً: 12 ب 345 ایران 11"
                value={manualPlate} onChange={(e) => setManualPlate(e.target.value)} />
              <RadioGroup row value={manualDir} onChange={(e) => setManualDir(e.target.value)}>
                <FormControlLabel value="IN" control={<Radio size="small" />} label="ورود" />
                <FormControlLabel value="OUT" control={<Radio size="small" />} label="خروج" />
              </RadioGroup>
              <Button variant="contained" startIcon={<TouchApp />} disabled={busy}
                onClick={() => sendManual()}>ثبت رویداد دستی</Button>
            </Stack>
            {manualResult && <Box mt={1.5}>{renderStepCard({ ...manualResult, title: `رویداد دستی — ${manualResult.plate_raw}` }, -1)}</Box>}
          </Box>
        )}

        {/* دفترچه گام‌ها */}
        {steps.length > 0 && (
          <Box mt={2}>
            <Typography fontWeight={800} mb={1}>📖 گام‌های اجراشده ({steps.length})</Typography>
            <Stack spacing={1}>{steps.map(renderStepCard)}</Stack>
          </Box>
        )}
      </CardContent></Card>

      {/* ================= شبیه‌ساز خودکار ================= */}
      <Card><CardContent>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} alignItems={{ sm: 'center' }} flexWrap="wrap" useFlexGap>
          {st?.running ? (
            <Button variant="contained" color="error" startIcon={<Stop />} onClick={() => act('stop')}>توقف</Button>
          ) : (
            <Button variant="contained" color="success" startIcon={<PlayArrow />}
              onClick={() => act('start', `?interval=${intervalNum}&resident_ratio=${ratio}`)}>شروع شبیه‌سازی</Button>
          )}
          <Button variant="outlined" startIcon={<TouchApp />} onClick={() => act('tick')}>یک رویداد دستی</Button>
          <Box sx={{ minWidth: 260, flex: 1, maxWidth: 420 }}>
            <Typography variant="caption" color="text.secondary">
              فاصله بین رویدادها: <b>{intervalNum}</b> ثانیه (۱ تا ۱۸۰)
            </Typography>
            <Slider size="small" min={1} max={180} step={1} marks={intervalMarks}
              value={intervalNum}
              onChange={(_, v) => setIntervalS(String(v as number))}
              valueLabelDisplay="auto" />
          </Box>
          <TextField size="small" type="number" label="فاصله (ثانیه)" sx={{ width: 120 }}
            inputProps={{ min: 1, max: 180 }}
            value={interval}
            onChange={(e) => {
              const v = Number(e.target.value)
              if (!Number.isNaN(v)) setIntervalS(String(Math.max(1, Math.min(180, Math.floor(v)))))
            }} />
          <Stack direction="row" spacing={0.6}>
            {['2', '3', '5', '10', '30', '60', '180'].map((v) => (
              <Chip key={v} size="small" clickable variant={interval === v ? 'filled' : 'outlined'}
                color={interval === v ? 'primary' : 'default'}
                label={`${v}s`} onClick={() => setIntervalS(v)} />
            ))}
          </Stack>
          <TextField size="small" select label="نسبت ساکن" value={ratio}
            onChange={(e) => setRatio(e.target.value)} sx={{ width: 140 }}>
            <MenuItem value="0.5">۵۰٪</MenuItem><MenuItem value="0.8">۸۰٪</MenuItem><MenuItem value="0.9">۹۰٪</MenuItem>
          </TextField>
        </Stack>
        <Stack direction="row" spacing={1.2} flexWrap="wrap" useFlexGap mt={2} alignItems="center">
          <Chip color={st?.running ? 'success' : 'default'} label={st?.running ? 'در حال اجرا' : 'متوقف'} />
          <Chip variant="outlined" label={`کل: ${st?.events ?? 0}`} />
          <Chip label={`ورود ساکن: ${st?.resident_entries ?? 0}`} color="success" variant="outlined" />
          <Chip label={`ورود مهمان: ${st?.guest_entries ?? 0}`} color="warning" variant="outlined" />
          <Chip label={`خروج: ${st?.exit ?? 0}`} color="secondary" variant="outlined" />
          <Chip label={`ممنوع/جریمه: ${st?.violations ?? 0}`} color="error" variant="outlined" />
          <Chip label={`🚗 داخل: ${st?.inside_count ?? 0}`} color="info" />
          <Chip label={`⏱ بیشترین توقف: ${dur(st?.max_stay_seconds)}`} color="primary" />
        </Stack>
      </CardContent></Card>

      <Card><CardContent>
        <Typography fontWeight={800} mb={1}>🗺 آمار ورود به تفکیک استان ({st?.provinces_total ?? 0} استان)</Typography>
        {provs.length === 0 && <Typography color="text.secondary">هنوز ورودی ثبت نشده.</Typography>}
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          {provs.map(([p, n]) => (
            <Chip key={p} label={`📍 ${p}: ${n}`}
              sx={{ bgcolor: `rgba(21,101,192,${Math.min(0.15 + n / 40, 0.85)})`, color: '#fff', fontWeight: 700 }} />
          ))}
        </Stack>
      </CardContent></Card>

      <Card><CardContent>
        <Typography fontWeight={800} mb={1}>🚦 جریان زنده ورود/خروج</Typography>
        {simEvents.length === 0 && <Typography color="text.secondary">شروع کنید...</Typography>}
        <Stack spacing={1}>
          {simEvents.map((e) => {
            const d = e.data as unknown as SimEvent
            return (
              <Stack key={e.event_id} direction={{ xs: 'column', sm: 'row' }} spacing={1.2}
                alignItems={{ sm: 'center' }} sx={{ border: '1px solid #E3EAF2', borderRadius: 2.5, p: 1.2 }}>
                <Chip size="small" color={d.direction === 'IN' ? 'primary' : 'secondary'}
                  label={d.direction === 'IN' ? '⬅ ورود' : 'خروج ➡'} sx={{ minWidth: 88 }} />
                <PlateBox plate={d.plate} size="sm" />
                {d.kind && <Chip size="small" variant="outlined"
                  label={d.kind === 'RESIDENT' ? 'ساکن' : 'مهمان'} />}
                <Chip size="small" color={colorOf(d.decision) as never}
                  label={decisionFa[d.decision ?? ''] ?? d.decision ?? '-'} />
                <Typography variant="caption" color="text.secondary" sx={{ flex: 1 }}>
                  {(d.province || d.city) ? `📍 ${d.province ?? '?'}${d.city ? ` — ${d.city}` : ''} | ` : ''}
                  {d.gate} — {decisionFa[d.reason ?? ''] ?? d.reason ?? ''}
                  {d.barrier === 'OPEN' ? ' — راهبند باز' : ''}
                  {typeof d.inside_count === 'number' ? ` — داخل: ${d.inside_count}` : ''}
                </Typography>
                <Typography variant="caption" color="text.secondary">{faDate(e.occurred_at)}</Typography>
              </Stack>
            )
          })}
        </Stack>
      </CardContent></Card>

      <Card><CardContent>
        <Typography fontWeight={800} mb={1}>🅿️ خودروهای داخل مجموعه ({inside?.count ?? 0}) — مرتب بر اساس طولانی‌ترین حضور</Typography>
        <Stack spacing={1}>
          {(inside?.items ?? []).slice(0, 15).map((r) => (
            <Stack key={r.plate} direction={{ xs: 'column', sm: 'row' }} spacing={1.2} alignItems={{ sm: 'center' }}
              sx={{ border: '1px solid #E3EAF2', borderRadius: 2.5, p: 1 }}>
              <PlateBox plate={r.plate} size="sm" />
              <Chip size="small" variant="outlined" label={r.kind === 'RESIDENT' ? 'ساکن' : 'مهمان'} />
              {(r.province || r.city) && (
                <Typography variant="caption" color="text.secondary">
                  {'\u{1F4CD}'} {r.province ?? '?'}{r.city ? ` — ${r.city}` : ''}
                </Typography>
              )}
              <Typography variant="caption" sx={{ flex: 1, fontWeight: 800 }}>مدت حضور: {dur(r.seconds)}</Typography>
            </Stack>
          ))}
          {(inside?.items ?? []).length === 0 && <Typography color="text.secondary">مجموعه خالی است.</Typography>}
        </Stack>
      </CardContent></Card>

      <Card><CardContent>
        <Typography fontWeight={800} mb={1}>⏱ بیشترین مدت‌های توقف (خروج‌های انجام‌شده)</Typography>
        <Stack spacing={1}>
          {(durs?.items ?? []).slice(0, 12).map((r, i) => (
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
              <Typography variant="body2" fontWeight={800}>⏱ {dur(r.seconds)}</Typography>
              <Typography variant="caption" color="text.secondary">{faDate(r.to)}</Typography>
            </Stack>
          ))}
          {(durs?.items ?? []).length === 0 && <Typography color="text.secondary">هنوز خروجی ثبت نشده.</Typography>}
        </Stack>
      </CardContent></Card>

      <Divider />
      <Typography variant="caption" color="text.secondary">
        نکته: قوانین فعال‌شده در سناریو را می‌توانی از صفحه «قوانین ورود/خروج» دوباره به DRAFT برگردانی.
      </Typography>
    </Stack>
  )
}
