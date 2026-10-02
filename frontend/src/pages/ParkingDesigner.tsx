import { useMemo, useState, type FormEvent, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, Box, Button, Card, CardContent, Chip, Dialog, DialogActions, DialogContent,
  DialogTitle, FormControlLabel, IconButton, MenuItem, Stack, Switch, Tab, Tabs,
  TextField, Typography,
} from '@mui/material'
import { Add, ArrowDownward, ArrowUpward, Delete, Edit, Rule as RuleIcon, Save, Settings, Tune } from '@mui/icons-material'
import { api, apiErrorFa } from '../api/client'
import JalaliDateTime from '../components/JalaliDateTime'

// ---------------- انواع ----------------
interface VGroup { id: string; code: string; title: string; description?: string | null; membership_kind: string; is_active: boolean; sort_order: number; default_tariff_id?: string | null }
interface Cond { field: string; op: string; value?: unknown }
interface Act { action: string; params?: Record<string, unknown> }
interface Rule { id: string; name: string; description?: string | null; direction: string; priority: number; enabled: boolean; condition_mode: string; conditions: Cond[]; actions: Act[]; status: string; effective_from?: string | null }
interface SettingResp { key: string; value: Record<string, unknown>; is_default: boolean; updated_at?: string | null }
interface HistRow { id: string; old_value: Record<string, unknown> | null; new_value: Record<string, unknown> | null; reason?: string | null; changed_at?: string | null }
interface ReceiptTpl { id: string; name: string; is_active: boolean; paper_width_mm: number; sections: { key: string; visible: boolean }[]; header_text?: string | null; footer_text?: string | null; show_trial_badge: boolean }
interface BoxCfg { id: string; side: string; is_active: boolean; buttons: { key: string; label: string; visible: boolean }[]; messages: Record<string, string>; font_scale: number; colors: Record<string, string> }
interface RuleDraft { id?: string; name: string; description: string; direction: string; priority: number; enabled: boolean; condition_mode: string; conditions: Cond[]; actions: Act[]; effective_from: string }

// ---------------- کاتالوگ شرایط/اقدامات (whitelist — مطابق موتور واقعی) ----------------
const FIELDS: { code: string; fa: string; ops: string[]; kind: 'bool' | 'num' | 'text' | 'member' | 'time' | 'plates' }[] = [
  { code: 'membership_kind', fa: 'گروه خودرو', ops: ['eq', 'in'], kind: 'member' },
  { code: 'is_resident', fa: 'ساکن است', ops: ['true', 'false'], kind: 'bool' },
  { code: 'has_valid_permit', fa: 'حق استفاده معتبر دارد', ops: ['true', 'false'], kind: 'bool' },
  { code: 'yard_full', fa: 'ظرفیت محوطه پر است', ops: ['true', 'false'], kind: 'bool' },
  { code: 'covered_free_count', fa: 'جایگاه مسقف آزاد', ops: ['gte', 'lte', 'eq'], kind: 'num' },
  { code: 'has_open_session', fa: 'جلسه توقف فعال دارد', ops: ['true', 'false'], kind: 'bool' },
  { code: 'has_debt', fa: 'بدهی قبلی دارد', ops: ['true', 'false'], kind: 'bool' },
  { code: 'confirmed_violations_count', fa: 'تخلف تأییدشده (تعداد)', ops: ['gte', 'lte', 'eq'], kind: 'num' },
  { code: 'driver_request', fa: 'درخواست راننده', ops: ['eq'], kind: 'text' },
  { code: 'time_window', fa: 'بازه زمانی', ops: ['time_window'], kind: 'time' },
  { code: 'gate_code', fa: 'کد گیت', ops: ['eq'], kind: 'text' },
  { code: 'plate_in', fa: 'پلاک در فهرست', ops: ['in'], kind: 'plates' },
]
const OPS_FA: Record<string, string> = {
  true: 'برقرار است', false: 'برقرار نیست', eq: 'مساوی', ne: 'مخالف',
  in: 'یکی از', not_in: 'هیچ‌کدام از', gte: 'حداقل', lte: 'حداکثر', time_window: 'در بازه',
}
const ACTIONS: { code: string; fa: string; param?: 'text' | 'reason' }[] = [
  { code: 'show_message', fa: 'نمایش پیام', param: 'text' },
  { code: 'require_driver_selection', fa: 'درخواست انتخاب نوع استفاده' },
  { code: 'refer_to_guard', fa: 'ارجاع به نگهبان' },
  { code: 'deny', fa: 'رد عبور' },
  { code: 'allow_with_warning', fa: 'اجازه عبور با هشدار' },
  { code: 'notify_field_op', fa: 'اعلان به مسئول محوطه' },
  { code: 'issue_receipt', fa: 'صدور قبض' },
  { code: 'request_payment', fa: 'درخواست پرداخت' },
]
const MEMBERSHIP_FA: Record<string, string> = {
  PRIMARY_WITH_COVERED: 'اصلی — پارکینگ مسقف', SECONDARY_WITH_COVERED: 'جایگزین — پارکینگ مسقف',
  RESIDENT_YARD: 'ساکن — متقاضی محوطه', NONRESIDENT_YARD: 'غیرساکن — متقاضی محوطه', SPECIAL_PERMIT: 'مجوز ویژه',
}
const fieldFa = (c: string) => FIELDS.find((f) => f.code === c)?.fa ?? c
const actionFa = (c: string) => ACTIONS.find((a) => a.code === c)?.fa ?? c

// ---------------- صفحه ----------------
export default function ParkingDesigner() {
  const qc = useQueryClient()
  const [tab, setTab] = useState(0)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const done = (m: string) => { setErr(''); setMsg(m) }

  // ===== داده‌های مشترک =====
  const { data: groups } = useQuery({ queryKey: ['vgroups'], queryFn: async () => (await api.get('/vehicle-groups')).data as VGroup[] })
  const { data: rules } = useQuery({ queryKey: ['erules'], queryFn: async () => (await api.get('/rules')).data as Rule[] })
  const { data: tariffPol } = useQuery({ queryKey: ['set', 'tariff_policy'], queryFn: async () => (await api.get('/app-settings/tariff_policy')).data as SettingResp })
  const { data: violPol } = useQuery({ queryKey: ['set', 'violation_policy'], queryFn: async () => (await api.get('/app-settings/violation_policy')).data as SettingResp })
  const { data: receipts } = useQuery({ queryKey: ['receipts'], queryFn: async () => (await api.get('/receipt-templates')).data as ReceiptTpl[] })
  const { data: boxIn } = useQuery({ queryKey: ['box', 'IN'], queryFn: async () => (await api.get('/box-settings/IN')).data as BoxCfg })
  const { data: boxOut } = useQuery({ queryKey: ['box', 'OUT'], queryFn: async () => (await api.get('/box-settings/OUT')).data as BoxCfg })
  const { data: capacity } = useQuery({ queryKey: ['cap-status'], queryFn: async () => (await api.get('/parking/capacity-status')).data as Record<string, unknown> })

  const invalidateAll = () => {
    ;['vgroups', 'erules', 'set', 'receipts', 'box'].forEach((k) => qc.invalidateQueries({ queryKey: [k] }))
  }

  // ================= تب ۱: گروه‌های خودرو =================
  const [gDlg, setGDlg] = useState<null | Partial<VGroup>>(null)
  const saveGroup = useMutation({
    mutationFn: async () => {
      const g = gDlg as Partial<VGroup>
      if (g.id) return (await api.patch(`/vehicle-groups/${g.id}`, g)).data
      return (await api.post('/vehicle-groups', g)).data
    },
    onSuccess: () => { setGDlg(null); done('گروه ذخیره شد'); invalidateAll() },
    onError: (e) => setErr(apiErrorFa(e)),
  })

  // ================= تب‌های ۲–۳: قانون‌ساز =================
  const emptyRule = (direction: string): RuleDraft => ({
    name: '', description: '', direction, priority: 100, enabled: true,
    condition_mode: 'ALL', conditions: [], actions: [], effective_from: '',
  })
  const [rDlg, setRDlg] = useState<null | RuleDraft>(null)
  const [delDlg, setDelDlg] = useState(false)
  const saveRule = useMutation({
    mutationFn: async () => {
      const r = rDlg as RuleDraft
      const body = { ...r, effective_from: r.effective_from || null }
      if (r.id) return (await api.patch(`/rules/${r.id}`, body)).data
      return (await api.post('/rules', body)).data
    },
    onSuccess: () => { setRDlg(null); done('قانون ذخیره شد (پیش‌نویس)'); invalidateAll() },
    onError: (e) => setErr(apiErrorFa(e)),
  })
  const publishRule = useMutation({
    mutationFn: async (p: { id: string; on: boolean }) =>
      p.on ? (await api.post(`/rules/${p.id}/publish`, { reason: 'publish from designer' })).data
           : (await api.post(`/rules/${p.id}/disable`)).data,
    onSuccess: () => { done('وضعیت قانون تغییر کرد'); invalidateAll() },
    onError: (e) => setErr(apiErrorFa(e)),
  })

  // ================= تب ۴–۵: تنظیمات سیاستی =================
  const saveSetting = useMutation({
    mutationFn: async (p: { key: string; value: Record<string, unknown> }) =>
      (await api.put(`/app-settings/${p.key}`, { value: p.value, reason: 'designer-edit' })).data,
    onSuccess: () => { done('تنظیمات ذخیره شد (با ثبت در تاریخچه)'); invalidateAll() },
    onError: (e) => setErr(apiErrorFa(e)),
  })
  const [tariffDraft, setTariffDraft] = useState<Record<string, unknown> | null>(null)
  const [violDraft, setViolDraft] = useState<Record<string, unknown> | null>(null)
  const tVal = (tariffDraft ?? tariffPol?.value ?? {}) as Record<string, number | string | string[]>
  const vVal = (violDraft ?? violPol?.value ?? {}) as Record<string, number | string | string[]>

  // ================= تب ۶: باکس‌ها =================
  const [boxSide, setBoxSide] = useState<'IN' | 'OUT'>('IN')
  const box = boxSide === 'IN' ? boxIn : boxOut
  const [boxDraft, setBoxDraft] = useState<BoxCfg | null>(null)
  const openBox = () => { if (box) { setBoxDraft(JSON.parse(JSON.stringify(box))); setErr('') } }
  const saveBox = useMutation({
    mutationFn: async () => (await api.put(`/box-settings/${boxSide}`, boxDraft)).data,
    onSuccess: () => { setBoxDraft(null); done('تنظیمات باکس ذخیره شد'); invalidateAll() },
    onError: (e) => setErr(apiErrorFa(e)),
  })

  // ================= تب ۷: طراح قبض =================
  const activeReceipt = (receipts ?? []).find((t) => t.is_active) ?? (receipts ?? [])[0]
  const [rcDraft, setRcDraft] = useState<ReceiptTpl | null>(null)
  const openReceipt = () => { if (activeReceipt) { setRcDraft(JSON.parse(JSON.stringify(activeReceipt))); setErr('') } }
  const saveReceipt = useMutation({
    mutationFn: async () => (await api.put(`/receipt-templates/${(rcDraft as ReceiptTpl).id}`, rcDraft)).data,
    onSuccess: () => { setRcDraft(null); done('قالب قبض ذخیره شد'); invalidateAll() },
    onError: (e) => setErr(apiErrorFa(e)),
  })
  const moveSection = <T,>(arr: T[], i: number, dir: -1 | 1): T[] => {
    const j = i + dir
    if (j < 0 || j >= arr.length) return arr
    const c = [...arr]; [c[i], c[j]] = [c[j], c[i]]; return c
  }

  // ================= تب ۹: ماشین‌حساب تعرفه =================
  const [calcIn, setCalcIn] = useState('2026-10-02T08:00')
  const [calcOut, setCalcOut] = useState('2026-10-02T11:30')
  const calc = useMemo(() => {
    const a = new Date(calcIn), b = new Date(calcOut)
    if (isNaN(a.getTime()) || isNaN(b.getTime())) return null
    const sec = Math.max(0, Math.round((b.getTime() - a.getTime()) / 1000))
    const free = Number(tVal.free_minutes ?? 0) * 60
    const billable = Math.max(0, sec - free)
    const hours = Math.ceil(billable / 3600)
    const rate = Number(tVal.hourly_amount ?? 0)
    const raw = hours * rate
    const cap = Number(tVal.daily_max_amount ?? 0)
    const days = Math.max(1, Math.ceil(sec / 86400))
    const capped = cap > 0 && raw > cap * days
    const steps = [
      `مدت توقف: ${Math.floor(sec / 3600)} ساعت و ${Math.floor((sec % 3600) / 60)} دقیقه`,
      `مهلت رایگان: ${Number(tVal.free_minutes ?? 0)} دقیقه → زمان مشمول: ${Math.floor(billable / 60)} دقیقه`,
      `گردکردن ساعتی: ${hours} ساعت × ${rate.toLocaleString('fa-IR')} ریال`,
    ]
    if (capped) steps.push(`اعمال سقف روزانه (${cap.toLocaleString('fa-IR')} × ${days} روز)`)
    return { sec, free, billable, hours, raw, final: capped ? cap * days : raw, capped, days, steps }
  }, [calcIn, calcOut, tVal])
  const calcPreview = useMutation({
    mutationFn: async (seconds: number) =>
      (await api.post('/tariffs/preview', { duration_seconds: seconds })).data as Record<string, unknown>,
  })

  // ================= تب ۱۰: تاریخچه =================
  const [histKey, setHistKey] = useState('tariff_policy')
  const { data: history } = useQuery({
    queryKey: ['hist', histKey],
    queryFn: async () => (await api.get(`/app-settings/${histKey}/history`)).data as HistRow[],
  })
  const revert = useMutation({
    mutationFn: async (p: { key: string; value: Record<string, unknown> }) =>
      (await api.put(`/app-settings/${p.key}`, { value: p.value, reason: 'REVERT from history' })).data,
    onSuccess: () => { done('نسخه قبلی بازگردانی شد'); invalidateAll() },
    onError: (e) => setErr(apiErrorFa(e)),
  })

  const tabNames = ['گروه‌های خودرو', 'قوانین ورود', 'قوانین خروج', 'تعرفه و تخفیف', 'تخلفات',
    'باکس ورود/خروج', 'طراح قبض', 'نقشه پارکینگ', 'شبیه‌سازی', 'تاریخچه تغییرات']

  const ruleList = (direction: string) => (rules ?? []).filter((r) => r.direction === direction || r.direction === 'ANY')

  const RuleCard = ({ r }: { r: Rule }) => (
    <Card><CardContent sx={{ py: 1.5 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" useFlexGap>
        <Stack direction="row" spacing={1} alignItems="center">
          <Typography fontWeight={800}>{r.name}</Typography>
          <Chip size="small" label={r.direction === 'ANY' ? 'ورود و خروج' : r.direction === 'IN' ? 'ورود' : 'خروج'} />
          <Chip size="small" color={r.status === 'ACTIVE' ? 'success' : r.status === 'DRAFT' ? 'warning' : 'default'}
            label={r.status === 'ACTIVE' ? 'فعال' : r.status === 'DRAFT' ? 'پیش‌نویس' : 'غیرفعال'} />
          <Chip size="small" variant="outlined" label={`اولویت ${r.priority}`} />
        </Stack>
        <Stack direction="row" spacing={0.5}>
          <IconButton size="small" onClick={() => setRDlg({ ...r, description: r.description ?? '', effective_from: r.effective_from ?? '' })}><Edit fontSize="small" /></IconButton>
          {r.status === 'ACTIVE'
            ? <Button size="small" color="warning" onClick={() => publishRule.mutate({ id: r.id, on: false })}>غیرفعال‌سازی</Button>
            : <Button size="small" color="success" onClick={() => publishRule.mutate({ id: r.id, on: true })}>انتشار</Button>}
        </Stack>
      </Stack>
      <Typography variant="caption" color="text.secondary">
        اگر {r.condition_mode === 'ALL' ? 'همه' : 'یکی از'} شرایط: {r.conditions.map((c) => fieldFa(c.field)).join(' و ')}
        {' → '}
        {r.actions.map((a) => actionFa(a.action)).join('، ')}
      </Typography>
    </CardContent></Card>
  )

  const CondRow = ({ c, onChange, onDelete }: { c: Cond; onChange: (n: Cond) => void; onDelete: () => void }) => {
    const meta = FIELDS.find((f) => f.code === c.field)
    return (
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <TextField select size="small" label="شرط" value={c.field} sx={{ minWidth: 180 }}
          onChange={(e) => { const f = FIELDS.find((x) => x.code === e.target.value)!; onChange({ field: f.code, op: f.ops[0] }) }}>
          {FIELDS.map((f) => <MenuItem key={f.code} value={f.code}>{f.fa}</MenuItem>)}
        </TextField>
        <TextField select size="small" label="شرطِ" value={c.op} sx={{ minWidth: 120 }}
          onChange={(e) => onChange({ ...c, op: e.target.value })}>
          {(meta?.ops ?? []).map((o) => <MenuItem key={o} value={o}>{OPS_FA[o] ?? o}</MenuItem>)}
        </TextField>
        {meta?.kind === 'bool' && (
          <Switch checked={c.op === 'true'} onChange={(e) => onChange({ ...c, op: e.target.checked ? 'true' : 'false' })} />
        )}
        {meta?.kind === 'num' && (
          <TextField size="small" type="number" label="مقدار" value={String(c.value ?? 0)} sx={{ width: 110 }}
            onChange={(e) => onChange({ ...c, value: Number(e.target.value) })} />
        )}
        {meta?.kind === 'text' && (
          <TextField size="small" label="مقدار" value={String(c.value ?? '')} sx={{ width: 140 }}
            onChange={(e) => onChange({ ...c, value: e.target.value })} />
        )}
        {meta?.kind === 'member' && (
          <TextField size="small" select label="گروه" value={String(c.value ?? '')} sx={{ minWidth: 200 }}
            onChange={(e) => onChange({ ...c, value: e.target.value })}>
            {Object.entries(MEMBERSHIP_FA).map(([k, v]) => <MenuItem key={k} value={k}>{v}</MenuItem>)}
          </TextField>
        )}
        {meta?.kind === 'time' && (
          <Stack direction="row" spacing={1}>
            <TextField size="small" type="time" label="از" value={String((c.value as { from?: string })?.from ?? '08:00')}
              onChange={(e) => onChange({ ...c, value: { from: e.target.value, to: String((c.value as { to?: string })?.to ?? '20:00') } })} />
            <TextField size="small" type="time" label="تا" value={String((c.value as { to?: string })?.to ?? '20:00')}
              onChange={(e) => onChange({ ...c, value: { from: String((c.value as { from?: string })?.from ?? '08:00'), to: e.target.value } })} />
          </Stack>
        )}
        {meta?.kind === 'plates' && (
          <TextField size="small" label="پلاک‌ها با ویرگول" value={String(c.value ?? '')} sx={{ minWidth: 260 }}
            onChange={(e) => onChange({ ...c, value: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })} />
        )}
        <IconButton size="small" color="error" onClick={onDelete}><Delete fontSize="small" /></IconButton>
      </Stack>
    )
  }

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Settings color="primary" />
          <Typography variant="h6" fontWeight={800}>طراح قوانین و تنظیمات پارکینگ</Typography>
        </Stack>
        <Chip size="small" variant="outlined" label="بدون نیاز به برنامه‌نویسی" />
      </Stack>
      {err && <Alert severity="error">{err}</Alert>}
      {msg && <Alert severity="success">{msg}</Alert>}

      <Tabs value={tab} onChange={(_, v: number) => setTab(v)} variant="scrollable" scrollButtons sx={{ bgcolor: '#fff', borderRadius: 2, px: 1 }}>
        {tabNames.map((t) => <Tab key={t} label={t} />)}
      </Tabs>

      {/* ===== ۰: گروه‌های خودرو ===== */}
      {tab === 0 && (
        <Stack spacing={2}>
          <Stack direction="row" justifyContent="flex-end">
            <Button variant="contained" startIcon={<Add />} onClick={() => setGDlg({ title: '', code: '', membership_kind: 'NONRESIDENT_YARD', is_active: true, sort_order: 0 })}>گروه جدید</Button>
          </Stack>
          <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 2 }}>
            {(groups ?? []).map((g) => (
              <Card key={g.id}><CardContent sx={{ py: 1.5 }}>
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                  <Stack>
                    <Typography fontWeight={800}>{g.title} <Typography component="span" variant="caption" color="text.secondary">({g.code})</Typography></Typography>
                    <Typography variant="caption" color="text.secondary">{MEMBERSHIP_FA[g.membership_kind] ?? g.membership_kind} — {g.description ?? 'بدون توضیح'}</Typography>
                  </Stack>
                  <Stack direction="row" spacing={0.5} alignItems="center">
                    <Chip size="small" color={g.is_active ? 'success' : 'default'} label={g.is_active ? 'فعال' : 'غیرفعال'} />
                    <IconButton size="small" onClick={() => setGDlg({ ...g })}><Edit fontSize="small" /></IconButton>
                  </Stack>
                </Stack>
              </CardContent></Card>
            ))}
          </Box>
        </Stack>
      )}

      {/* ===== ۱–۲: قوانین ورود/خروج ===== */}
      {(tab === 1 || tab === 2) && (() => {
        const dir = tab === 1 ? 'IN' : 'OUT'
        return (
          <Stack spacing={2}>
            <Stack direction="row" justifyContent="flex-end">
              <Button variant="contained" startIcon={<RuleIcon />} onClick={() => setRDlg(emptyRule(dir))}>قانون جدید</Button>
            </Stack>
            <Alert severity="info" variant="outlined">
              ترتیب اجرا از اولویت کوچک‌تر است. قوانین فقط می‌توانند تصمیم سیستم را «سخت‌گیرانه‌تر» یا برای پلاک ناشناسِ متقاضی محوطه «مسیر کنترل‌شده» باز کنند؛ محدودیت‌ها و موارد غیرفعال را نمی‌شکنند و بازکردن راهبند فقط از مسیر تصمیم سرور می‌گذرد.
            </Alert>
            {ruleList(dir).map((r) => <RuleCard key={r.id} r={r} />)}
            {ruleList(dir).length === 0 && <Alert severity="info">قانونی تعریف نشده — رفتار پیش‌فرض سیستم اجرا می‌شود.</Alert>}
          </Stack>
        )
      })()}

      {/* ===== ۳: تعرفه و تخفیف ===== */}
      {tab === 3 && (
        <Stack spacing={2}>
          <Card><CardContent>
            <Typography fontWeight={800} mb={1}>سیاست تعرفه (مقادیر پیش‌نویس — پیش از اجرای مالی نیازمند تصویب)</Typography>
            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(3, 1fr)' }, gap: 2 }}>
              <TextField size="small" type="number" label="مهلت رایگان (دقیقه)" value={String(tVal.free_minutes ?? 0)}
                onChange={(e) => setTariffDraft({ ...tVal, free_minutes: Number(e.target.value) })} />
              <TextField size="small" type="number" label="نرخ ساعتی (ریال)" value={String(tVal.hourly_amount ?? 0)}
                onChange={(e) => setTariffDraft({ ...tVal, hourly_amount: Number(e.target.value) })} />
              <TextField size="small" type="number" label="سقف روزانه (ریال)" value={String(tVal.daily_max_amount ?? 0)}
                onChange={(e) => setTariffDraft({ ...tVal, daily_max_amount: Number(e.target.value) })} />
              <TextField size="small" select label="روش گردکردن" value={String(tVal.rounding ?? 'HOUR_UP')}
                onChange={(e) => setTariffDraft({ ...tVal, rounding: e.target.value })}>
                <MenuItem value="HOUR_UP">ساعتی رو به بالا</MenuItem>
                <MenuItem value="MINUTE">دقیقه‌ای</MenuItem>
              </TextField>
              <TextField size="small" select label="تعریف روز" value={String(tVal.day_definition ?? 'CALENDAR')}
                onChange={(e) => setTariffDraft({ ...tVal, day_definition: e.target.value })}>
                <MenuItem value="CALENDAR">روز تقویمی</MenuItem>
                <MenuItem value="24H">دوره ۲۴ ساعته از ورود</MenuItem>
              </TextField>
              <TextField size="small" type="number" label="مهلت خروج پس از پرداخت (دقیقه)" value={String(tVal.exit_grace_minutes ?? 0)}
                onChange={(e) => setTariffDraft({ ...tVal, exit_grace_minutes: Number(e.target.value) })} />
              <TextField size="small" type="number" label="تخفیف ساکنان (درصد)" value={String(tVal.resident_discount_percent ?? 0)}
                onChange={(e) => setTariffDraft({ ...tVal, resident_discount_percent: Number(e.target.value) })} />
            </Box>
            {Array.isArray(tVal._needs_decision) && (tVal._needs_decision as string[]).length > 0 && (
              <Alert severity="warning" sx={{ mt: 1.5 }}>موارد نیازمند تصمیم: {(tVal._needs_decision as string[]).join('، ')}</Alert>
            )}
            <Stack direction="row" justifyContent="flex-end" mt={2}>
              <Button variant="contained" startIcon={<Save />} onClick={() => saveSetting.mutate({ key: 'tariff_policy', value: tVal as Record<string, unknown> })}>ذخیره سیاست تعرفه</Button>
            </Stack>
          </CardContent></Card>

          <Card><CardContent>
            <Typography fontWeight={800} mb={1}>ماشین‌حساب آزمایشی (بر اساس سیاست بالا — بدون ثبت داده)</Typography>
            <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
              <JalaliDateTime label="زمان ورود" value={calcIn} onChange={(iso) => setCalcIn(iso)} />
              <JalaliDateTime label="زمان خروج" value={calcOut} onChange={(iso) => setCalcOut(iso)} />
              <Button variant="outlined" disabled={!calc} onClick={() => calc && calcPreview.mutate(calc.sec)}>تأیید با سرور</Button>
            </Stack>
            {calc && (
              <Box mt={2}>
                {calc.steps.map((s, i) => <Typography key={i} variant="body2">• {s}</Typography>)}
                <Typography fontWeight={800} mt={1}>
                  مبلغ نهایی (تخمین محلی): {calc.final.toLocaleString('fa-IR')} ریال
                </Typography>
                {calcPreview.data && (
                  <Alert severity="success" sx={{ mt: 1 }}>
                    نتیجه سرور: {Number(calcPreview.data.final ?? 0).toLocaleString('fa-IR')} ریال
                    {Array.isArray(calcPreview.data.warnings) && (calcPreview.data.warnings as string[]).length > 0
                      ? ` — هشدارها: ${(calcPreview.data.warnings as string[]).join('، ')}` : ''}
                  </Alert>
                )}
              </Box>
            )}
          </CardContent></Card>
        </Stack>
      )}

      {/* ===== ۴: تخلفات ===== */}
      {tab === 4 && (
        <Card><CardContent>
          <Typography fontWeight={800} mb={1}>سیاست تخلفات</Typography>
          <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 2 }}>
            <TextField size="small" type="number" label="جریمه پیشنهادی پیش‌فرض (ریال)" value={String(vVal.default_penalty_amount ?? 0)}
              onChange={(e) => setViolDraft({ ...vVal, default_penalty_amount: Number(e.target.value) })} />
            <FormControlLabel control={<Switch checked={Boolean(vVal.requires_image)} />}
              label="الزام تصویر برای ثبت تخلف"
              onChange={(_, ck: boolean) => setViolDraft({ ...vVal, requires_image: ck })} />
          </Box>
          <Typography variant="caption" color="text.secondary">
            یادآوری: تخلف تا پیش از تأیید بدهی قطعی نمی‌سازد و قفل چرخ/انسداد خروج خودکار وجود ندارد (سند §۱۵).
          </Typography>
          <Stack direction="row" justifyContent="flex-end" mt={2}>
            <Button variant="contained" startIcon={<Save />} onClick={() => saveSetting.mutate({ key: 'violation_policy', value: vVal as Record<string, unknown> })}>ذخیره</Button>
          </Stack>
        </CardContent></Card>
      )}

      {/* ===== ۵: باکس ورود/خروج ===== */}
      {tab === 5 && (
        <Stack spacing={2}>
          <Stack direction="row" spacing={1} alignItems="center">
            <TextField select size="small" label="باکس" value={boxSide} sx={{ width: 140 }}
              onChange={(e) => setBoxSide(e.target.value as 'IN' | 'OUT')}>
              <MenuItem value="IN">ورود</MenuItem>
              <MenuItem value="OUT">خروج</MenuItem>
            </TextField>
            <Button variant="contained" onClick={openBox} disabled={!box}>ویرایش این باکس</Button>
          </Stack>
          {box && !boxDraft && (
            <Card><CardContent>
              <Typography fontWeight={800} mb={1}>پیش‌نمایش زنده</Typography>
              <Box sx={{ maxWidth: 380, p: 2, borderRadius: 3, bgcolor: '#fff', border: `3px solid ${box.colors?.primary ?? '#1565C0'}` }}>
                <Typography sx={{ color: box.colors?.text }} fontSize={(14 * box.font_scale)} fontWeight={800}>{box.messages?.welcome}</Typography>
                <Stack spacing={1} mt={1.5}>
                  {box.buttons.filter((b) => b.visible).map((b) => (
                    <Box key={b.key} sx={{ py: 1, px: 2, borderRadius: 2, textAlign: 'center', color: '#fff', bgcolor: box.colors?.primary, fontSize: 15 * box.font_scale, fontWeight: 700 }}>
                      {b.label}
                    </Box>
                  ))}
                </Stack>
              </Box>
            </CardContent></Card>
          )}
          {boxDraft && (
            <Card><CardContent>
              <Typography fontWeight={800} mb={1}>ویرایش باکس {boxSide === 'IN' ? 'ورود' : 'خروج'}</Typography>
              {(boxDraft.buttons ?? []).map((b, i) => (
                <Stack key={i} direction="row" spacing={1} alignItems="center" mb={1}>
                  <TextField size="small" label="متن دکمه" value={b.label} fullWidth
                    onChange={(e) => setBoxDraft((p) => p ? { ...p, buttons: p.buttons.map((x, j) => j === i ? { ...x, label: e.target.value } : x) } : p)} />
                  <FormControlLabel control={<Switch checked={b.visible} />}
                    label="نمایش"
                    onChange={(_, ck: boolean) => setBoxDraft((p) => p ? { ...p, buttons: p.buttons.map((x, j) => j === i ? { ...x, visible: ck } : x) } : p)} />
                  <IconButton size="small" onClick={() => setBoxDraft((p) => p ? { ...p, buttons: moveSection(p.buttons, i, -1) } : p)}><ArrowUpward fontSize="small" /></IconButton>
                  <IconButton size="small" onClick={() => setBoxDraft((p) => p ? { ...p, buttons: moveSection(p.buttons, i, 1) } : p)}><ArrowDownward fontSize="small" /></IconButton>
                </Stack>
              ))}
              <Stack direction="row" spacing={2} mt={1}>
                <TextField size="small" fullWidth label="پیام خوش‌آمد" value={boxDraft.messages?.welcome ?? ''}
                  onChange={(e) => setBoxDraft((p) => p ? { ...p, messages: { ...p.messages, welcome: e.target.value } } : p)} />
                <TextField size="small" fullWidth label="پیام خطا" value={boxDraft.messages?.error ?? ''}
                  onChange={(e) => setBoxDraft((p) => p ? { ...p, messages: { ...p.messages, error: e.target.value } } : p)} />
                <TextField size="small" type="number" label="مقیاس متن" value={String(boxDraft.font_scale)}
                  onChange={(e) => setBoxDraft((p) => p ? { ...p, font_scale: Number(e.target.value) || 1 } : p)} sx={{ width: 130 }} />
                <TextField size="small" type="color" label="رنگ اصلی" value={boxDraft.colors?.primary ?? '#1565C0'}
                  onChange={(e) => setBoxDraft((p) => p ? { ...p, colors: { ...p.colors, primary: e.target.value } } : p)} sx={{ width: 110 }} />
              </Stack>
              <Stack direction="row" justifyContent="flex-end" spacing={1} mt={2}>
                <Button onClick={() => setBoxDraft(null)}>انصراف</Button>
                <Button variant="contained" onClick={() => saveBox.mutate()}>ذخیره باکس</Button>
              </Stack>
            </CardContent></Card>
          )}
        </Stack>
      )}

      {/* ===== ۶: طراح قبض ===== */}
      {tab === 6 && (
        <Stack spacing={2}>
          {!activeReceipt && <Alert severity="info">قالبی ثبت نشده است.</Alert>}
          {activeReceipt && !rcDraft && (
            <Stack direction="row" justifyContent="flex-end">
              <Button variant="contained" onClick={openReceipt}>ویرایش قالب فعال</Button>
            </Stack>
          )}
          {activeReceipt && !rcDraft && (
            <Card><CardContent>
              <Typography fontWeight={800} mb={1}>پیش‌نمایش (مقادیر نمونه)</Typography>
              <Box sx={{ width: activeReceipt.paper_width_mm * 3.2, mx: 'auto', p: 1.5, border: '1px dashed #999', bgcolor: '#fff' }}>
                {activeReceipt.sections.filter((s) => s.visible).map((s) => (
                  <Box key={s.key} sx={{ py: 0.4, borderBottom: '1px dotted #ccc', fontSize: 12 }}>
                    {{
                      complex_name: 'مجتمع مسکونی ارکیده',
                      receipt_id: 'شناسه قبض: RC-14050701-000123',
                      plate: 'پلاک: ۱۲ ب ۳۴۵ ایران ۶۷',
                      entry_time: 'زمان ورود: ۱۴۰۵/۰۷/۰۱ ۰۸:۳۰',
                      parking_spot: 'محل: P-12 (طبقه ۱)',
                      tariff_summary: 'تعرفه: ۹۰ دقیقه رایگان، ساعتی ۲۵۰٬۰۰۰ ریال',
                      trial_badge: '★ طرح آزمایشی — رایگان ★',
                      qr: '[QR]',
                      guide_text: 'لطفاً پیش از خروج تسویه کنید.',
                    }[s.key] ?? s.key}
                  </Box>
                ))}
                <Box mt={1} fontSize={11} color="text.secondary">{activeReceipt.footer_text ?? ''}</Box>
              </Box>
            </CardContent></Card>
          )}
          {rcDraft && (
            <Card><CardContent>
              <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap alignItems="center">
                <TextField size="small" label="نام قالب" value={rcDraft.name}
                  onChange={(e) => setRcDraft({ ...rcDraft, name: e.target.value })} />
                <TextField size="small" type="number" label="عرض کاغذ (mm)" value={String(rcDraft.paper_width_mm)} sx={{ width: 150 }}
                  onChange={(e) => setRcDraft({ ...rcDraft, paper_width_mm: Number(e.target.value) || 80 })} />
                <FormControlLabel control={<Switch checked={rcDraft.show_trial_badge} />} label="نشان «طرح آزمایشی — رایگان»"
                  onChange={(_, ck: boolean) => setRcDraft({ ...rcDraft, show_trial_badge: ck })} />
              </Stack>
              <TextField fullWidth size="small" label="متن سرصفحه" value={rcDraft.header_text ?? ''} margin="normal"
                onChange={(e) => setRcDraft({ ...rcDraft, header_text: e.target.value })} />
              <Typography fontWeight={800} mt={1}>اجزای قبض (ترتیب با فلش‌ها)</Typography>
              {rcDraft.sections.map((s, i) => (
                <Stack key={s.key} direction="row" spacing={1} alignItems="center" my={0.5}>
                  <Typography sx={{ width: 160 }} variant="body2">{s.key}</Typography>
                  <FormControlLabel control={<Switch checked={s.visible} />} label="نمایش"
                    onChange={(_, ck: boolean) => setRcDraft({ ...rcDraft, sections: rcDraft.sections.map((x, j) => j === i ? { ...x, visible: ck } : x) })} />
                  <IconButton size="small" onClick={() => setRcDraft({ ...rcDraft, sections: moveSection(rcDraft.sections, i, -1) })}><ArrowUpward fontSize="small" /></IconButton>
                  <IconButton size="small" onClick={() => setRcDraft({ ...rcDraft, sections: moveSection(rcDraft.sections, i, 1) })}><ArrowDownward fontSize="small" /></IconButton>
                </Stack>
              ))}
              <TextField fullWidth size="small" label="متن پایانی/راهنما" value={rcDraft.footer_text ?? ''} margin="normal"
                onChange={(e) => setRcDraft({ ...rcDraft, footer_text: e.target.value })} />
              <Stack direction="row" justifyContent="flex-end" spacing={1} mt={2}>
                <Button onClick={() => setRcDraft(null)}>انصراف</Button>
                <Button variant="contained" onClick={() => saveReceipt.mutate()}>ذخیره قالب</Button>
              </Stack>
            </CardContent></Card>
          )}
        </Stack>
      )}

      {/* ===== ۷: نقشه پارکینگ ===== */}
      {tab === 7 && (
        <Stack spacing={2}>
          <Card><CardContent>
            <Typography fontWeight={800} mb={1}>وضعیت ظرفیت (از داده واقعی)</Typography>
            <Typography>ظرفیت اعلامی: {String(capacity?.declared_capacity ?? '—')} — حضور تأییدشده: {String(capacity?.confirmed_presence ?? '—')} — پذیرش: {capacity?.accepting ? 'باز' : 'پر'}</Typography>
            <Typography variant="caption" color="text.secondary">نقشه کامل و جایگاه‌ها در صفحه «مسئول محوطه/پارکینگ» است؛ رنگ دستی روی تصویر به‌عنوان وضعیت قطعی اشغال استفاده نمی‌شود.</Typography>
          </CardContent></Card>
        </Stack>
      )}

      {/* ===== ۸: شبیه‌سازی ===== */}
      {tab === 8 && (
        <Alert severity="info">
          شبیه‌سازی سناریوهای ورود/خروج (بدون راهبند و پرداخت واقعی) در صفحه «شبیه‌ساز» منوی اصلی انجام می‌شود؛
          ماشین‌حساب تعرفه نیز در تب «تعرفه و تخفیف» همین صفحه است. قوانین را در تب‌های ورود/خروج بسازید، منتشر کنید و سپس در شبیه‌ساز آزمایش کنید.
        </Alert>
      )}

      {/* ===== ۹: تاریخچه ===== */}
      {tab === 9 && (
        <Stack spacing={2}>
          <TextField select size="small" label="کلید تنظیمات" value={histKey} sx={{ width: 260 }}
            onChange={(e) => setHistKey(e.target.value)}>
            <MenuItem value="tariff_policy">سیاست تعرفه</MenuItem>
            <MenuItem value="violation_policy">سیاست تخلفات</MenuItem>
          </TextField>
          {(history ?? []).map((h) => (
            <Card key={h.id}><CardContent sx={{ py: 1.5 }}>
              <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" useFlexGap>
                <Typography variant="body2">علت: {h.reason ?? '—'} — {h.changed_at ?? ''}</Typography>
                {h.old_value && (
                  <Button size="small" onClick={() => revert.mutate({ key: histKey, value: h.old_value as Record<string, unknown> })}>
                    بازگردانی این نسخه
                  </Button>
                )}
              </Stack>
              <Typography variant="caption" color="text.secondary">
                قبلی: {JSON.stringify(h.old_value)} | جدید: {JSON.stringify(h.new_value)}
              </Typography>
            </CardContent></Card>
          ))}
          {(history ?? []).length === 0 && <Alert severity="info">تغییری ثبت نشده است.</Alert>}
        </Stack>
      )}

      {/* ===== دیالوگ گروه ===== */}
      <Dialog open={gDlg !== null} onClose={() => setGDlg(null)}>
        <DialogTitle>{(gDlg as Partial<VGroup> | null)?.id ? 'ویرایش گروه' : 'گروه جدید'}</DialogTitle>
        <DialogContent>
          <Stack direction="row" spacing={2} mt={1}>
            <TextField size="small" label="کد (لاتین)" value={(gDlg as Partial<VGroup> | null)?.code ?? ''} required
              disabled={!!(gDlg as Partial<VGroup> | null)?.id}
              onChange={(e) => setGDlg((p) => p ? { ...p, code: e.target.value } : p)} />
            <TextField size="small" label="نام نمایشی" value={(gDlg as Partial<VGroup> | null)?.title ?? ''} required fullWidth
              onChange={(e) => setGDlg((p) => p ? { ...p, title: e.target.value } : p)} />
          </Stack>
          <TextField fullWidth size="small" label="توضیح" value={(gDlg as Partial<VGroup> | null)?.description ?? ''} margin="normal"
            onChange={(e) => setGDlg((p) => p ? { ...p, description: e.target.value } : p)} />
          <Stack direction="row" spacing={2} mt={1}>
            <TextField select size="small" label="حق پارکینگ / نوع استفاده" fullWidth
              value={(gDlg as Partial<VGroup> | null)?.membership_kind ?? 'NONRESIDENT_YARD'}
              onChange={(e) => setGDlg((p) => p ? { ...p, membership_kind: e.target.value } : p)}>
              {Object.entries(MEMBERSHIP_FA).map(([k, v]) => <MenuItem key={k} value={k}>{v}</MenuItem>)}
            </TextField>
            <TextField size="small" type="number" label="ترتیب" sx={{ width: 110 }}
              value={String((gDlg as Partial<VGroup> | null)?.sort_order ?? 0)}
              onChange={(e) => setGDlg((p) => p ? { ...p, sort_order: Number(e.target.value) } : p)} />
            <FormControlLabel control={<Switch checked={Boolean((gDlg as Partial<VGroup> | null)?.is_active)} />}
              label="فعال"
              onChange={(_, ck: boolean) => setGDlg((p) => p ? { ...p, is_active: ck } : p)} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setGDlg(null)}>انصراف</Button>
          <Button variant="contained" disabled={saveGroup.isPending} onClick={() => saveGroup.mutate()}>ذخیره</Button>
        </DialogActions>
      </Dialog>

      {/* ===== دیالوگ قانون‌ساز ===== */}
      <Dialog open={rDlg !== null} onClose={() => setRDlg(null)} maxWidth="md" fullWidth>
        <DialogTitle>{(rDlg as RuleDraft | null)?.id ? 'ویرایش قانون' : 'قانون جدید'}</DialogTitle>
        <DialogContent dividers>
          <Stack direction="row" spacing={2} mt={1} flexWrap="wrap" useFlexGap>
            <TextField size="small" label="نام قانون" value={(rDlg as RuleDraft | null)?.name ?? ''} required sx={{ minWidth: 220 }}
              onChange={(e) => setRDlg((p) => p ? { ...p, name: e.target.value } : p)} />
            <TextField select size="small" label="جهت" value={(rDlg as RuleDraft | null)?.direction ?? 'IN'} sx={{ width: 130 }}
              onChange={(e) => setRDlg((p) => p ? { ...p, direction: e.target.value } : p)}>
              <MenuItem value="IN">ورود</MenuItem>
              <MenuItem value="OUT">خروج</MenuItem>
              <MenuItem value="ANY">هر دو</MenuItem>
            </TextField>
            <TextField size="small" type="number" label="اولویت" value={String((rDlg as RuleDraft | null)?.priority ?? 100)} sx={{ width: 110 }}
              onChange={(e) => setRDlg((p) => p ? { ...p, priority: Number(e.target.value) } : p)} />
            <JalaliDateTime label="تاریخ اجرا" value={(rDlg as RuleDraft | null)?.effective_from ?? ''}
              onChange={(iso) => setRDlg((p) => p ? { ...p, effective_from: iso } : p)} />
            <FormControlLabel control={<Switch checked={Boolean((rDlg as RuleDraft | null)?.enabled)} />} label="فعال"
              onChange={(_, ck: boolean) => setRDlg((p) => p ? { ...p, enabled: ck } : p)} />
          </Stack>

          <Typography fontWeight={800} mt={2}>اگر (شرایط)</Typography>
          <TextField select size="small" label="ترکیب شرایط" value={(rDlg as RuleDraft | null)?.condition_mode ?? 'ALL'} sx={{ width: 220, mb: 1 }}
            onChange={(e) => setRDlg((p) => p ? { ...p, condition_mode: e.target.value } : p)}>
            <MenuItem value="ALL">همه شرایط برقرار باشد</MenuItem>
            <MenuItem value="ANY">حداقل یکی برقرار باشد</MenuItem>
          </TextField>
          {(rDlg as RuleDraft | null)?.conditions.map((c, i) => (
            <CondRow key={i} c={c}
              onChange={(nc) => setRDlg((p) => p ? { ...p, conditions: p.conditions.map((x, j) => j === i ? nc : x) } : p)}
              onDelete={() => setRDlg((p) => p ? { ...p, conditions: p.conditions.filter((_, j) => j !== i) } : p)} />
          ))}
          <Button size="small" startIcon={<Add />} onClick={() => setRDlg((p) => p ? { ...p, conditions: [...p.conditions, { field: 'is_resident', op: 'true' }] } : p)}>
            افزودن شرط
          </Button>

          <Typography fontWeight={800} mt={2}>آنگاه (اقدامات به‌ترتیب)</Typography>
          {(rDlg as RuleDraft | null)?.actions.map((a, i) => {
            const meta = ACTIONS.find((x) => x.code === a.action)
            return (
              <Stack key={i} direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap mb={1}>
                <TextField select size="small" label="اقدام" value={a.action} sx={{ minWidth: 240 }}
                  onChange={(e) => setRDlg((p) => p ? { ...p, actions: p.actions.map((x, j) => j === i ? { action: e.target.value } : x) } : p)}>
                  {ACTIONS.map((x) => <MenuItem key={x.code} value={x.code}>{x.fa}</MenuItem>)}
                </TextField>
                {meta?.param === 'text' && (
                  <TextField size="small" label="متن پیام" fullWidth value={String(a.params?.text ?? '')}
                    onChange={(e) => setRDlg((p) => p ? { ...p, actions: p.actions.map((x, j) => j === i ? { ...x, params: { ...x.params, text: e.target.value } } : x) } : p)} />
                )}
                <IconButton size="small" onClick={() => setRDlg((p) => p ? { ...p, actions: moveSection(p.actions, i, -1) } : p)}><ArrowUpward fontSize="small" /></IconButton>
                <IconButton size="small" onClick={() => setRDlg((p) => p ? { ...p, actions: moveSection(p.actions, i, 1) } : p)}><ArrowDownward fontSize="small" /></IconButton>
                <IconButton size="small" color="error"
                  onClick={() => setRDlg((p) => p ? { ...p, actions: p.actions.filter((_, j) => j !== i) } : p)}><Delete fontSize="small" /></IconButton>
              </Stack>
            )
          })}
          <Button size="small" startIcon={<Add />} onClick={() => setRDlg((p) => p ? { ...p, actions: [...p.actions, { action: 'show_message', params: { text: '' } }] } : p)}>
            افزودن اقدام
          </Button>
          <Alert severity="warning" variant="outlined" sx={{ mt: 2 }}>
            در صورت نبود قانون منطبق، مسیر پیش‌فرض ایمن سیستم اجرا می‌شود. قوانین اجازه نرم‌کردن محدودیت‌ها (پلاک محدود/خودرو غیرفعال) را ندارند.
          </Alert>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRDlg(null)}>انصراف</Button>
          <Button variant="contained" disabled={saveRule.isPending || !(rDlg as RuleDraft | null)?.name} onClick={() => saveRule.mutate()}>ذخیره (پیش‌نویس)</Button>
        </DialogActions>
      </Dialog>
    </Stack>
  )
}
