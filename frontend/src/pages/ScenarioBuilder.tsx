import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, Box, Button, Card, CardContent, Checkbox, Chip, Dialog, DialogActions,
  DialogContent, DialogTitle, FormControlLabel, Grid, MenuItem, Stack, Tab,
  Tabs, TextField, Typography,
} from '@mui/material'
import {
  Add, CleaningServices, Delete, PlayArrow, Refresh, Science, Summarize,
} from '@mui/icons-material'
import { api, apiErrorFa } from '../api/client'

interface Summary {
  complexes: number; towers: number; units: number; residents: number
  vehicles: number; permits: number; parking_spaces: number
  sessions: number; rules: number; users: number
}

const PURGE_CATEGORIES: { key: string; fa: string }[] = [
  { key: 'events_sessions', fa: 'رویدادها و جلسات توقف' },
  { key: 'finance', fa: 'مالی (پرداخت/شارژ)' },
  { key: 'violations', fa: 'تخلفات' },
  { key: 'vehicles', fa: 'خودروها و مجوزها' },
  { key: 'persons', fa: 'ساکنان' },
  { key: 'units', fa: 'واحدها' },
  { key: 'towers', fa: 'برج‌ها' },
  { key: 'complexes', fa: 'مجتمع‌ها' },
  { key: 'parking_spaces', fa: 'جایگاه‌های پارکینگ' },
  { key: 'rules', fa: 'قوانین ورود/خروج' },
  { key: 'users', fa: 'کاربران (غیر ادمین)' },
]

export default function ScenarioBuilder() {
  const qc = useQueryClient()
  const [err, setErr] = useState(''); const [msg, setMsg] = useState('')
  const [purgeSel, setPurgeSel] = useState<string[]>([])
  const [confirmPurge, setConfirmPurge] = useState(false)
  const [tab, setTab] = useState(0)

  // add-unit
  const [unitNumber, setUnitNumber] = useState('')
  const [unitFloor, setUnitFloor] = useState(1)
  // add-resident
  const [resUnit, setResUnit] = useState('')
  const [resFirst, setResFirst] = useState(''); const [resLast, setResLast] = useState('')
  const [resMobile, setResMobile] = useState(''); const [resType, setResType] = useState('OWNER')
  // add-vehicle
  const [vehPlate, setVehPlate] = useState(''); const [vehUnit, setVehUnit] = useState('')
  const [vehPerson, setVehPerson] = useState(''); const [vehBrand, setVehBrand] = useState('')
  const [vehColor, setVehColor] = useState('')

  const invalidate = () => qc.invalidateQueries({ queryKey: ['scenario'] })

  const { data: summary } = useQuery({
    queryKey: ['scenario'], queryFn: async () => (await api.get('/scenario/summary')).data as Summary,
  })
  const { data: units } = useQuery({
    queryKey: ['units'], queryFn: async () => (await api.get('/units')).data as { id: string; unit_number: string }[],
  })
  const { data: persons } = useQuery({
    queryKey: ['persons'], queryFn: async () => (await api.get('/persons')).data as { id: string; first_name: string; last_name: string }[],
  })

  const doPurge = useMutation({
    mutationFn: async (cats: string[]) => (await api.post('/scenario/purge', { categories: cats })).data as Record<string, number>,
    onSuccess: (d) => {
      setErr(''); setConfirmPurge(false)
      const txt = Object.entries(d).filter(([, v]) => v > 0).map(([k, v]) => `${k}: ${v}`).join(' | ') || 'هیچ'
      setMsg(`پاکسازی انجام شد → ${txt}`); invalidate()
    },
    onError: (e) => setErr(apiErrorFa(e)),
  })
  const doSetup = useMutation({
    mutationFn: async () => (await api.post('/scenario/setup-default')).data,
    onSuccess: () => { setErr(''); setMsg('سناریوی پیش‌فرض ساخته شد (۲ ساکن × ۳ ماشین + ۲ غریبه + ۳ قانون DRAFT)'); invalidate() },
    onError: (e) => setErr(apiErrorFa(e)),
  })
  const addUnit = useMutation({
    mutationFn: async () => (await api.post('/scenario/add-unit', { unit_number: unitNumber, floor_number: unitFloor })).data,
    onSuccess: () => { setErr(''); setMsg(`واحد ${unitNumber} ذخیره شد`); setUnitNumber(''); invalidate() },
    onError: (e) => setErr(apiErrorFa(e)),
  })
  const addRes = useMutation({
    mutationFn: async () => (await api.post('/scenario/add-resident', {
      unit_id: resUnit, first_name: resFirst, last_name: resLast, mobile: resMobile || null, person_type: resType,
    })).data,
    onSuccess: () => { setErr(''); setMsg('ساکن ذخیره شد'); setResFirst(''); setResLast(''); setResMobile(''); invalidate() },
    onError: (e) => setErr(apiErrorFa(e)),
  })
  const addVeh = useMutation({
    mutationFn: async () => (await api.post('/scenario/add-vehicle', {
      person_id: vehPerson || null, unit_id: vehUnit || null,
      plate_raw: vehPlate, brand: vehBrand || null, color: vehColor || null,
    })).data,
    onSuccess: () => { setErr(''); setMsg('خودرو ذخیره شد'); setVehPlate(''); invalidate() },
    onError: (e) => setErr(apiErrorFa(e)),
  })

  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={1} alignItems="center">
        <Science color="primary" />
        <Typography variant="h6" fontWeight={800}>سناریوساز — ساخت و پاکسازی داده‌ها</Typography>
      </Stack>
      {err && <Alert severity="error">{err}</Alert>}
      {msg && <Alert severity="success">{msg}</Alert>}

      <Tabs value={tab} onChange={(_, v: number) => setTab(v)} variant="scrollable" scrollButtons>
        <Tab label="پاکسازی" icon={<CleaningServices />} iconPosition="start" />
        <Tab label="افزودن دستی" icon={<Add />} iconPosition="start" />
        <Tab label="سناریوی پیش‌فرض" icon={<PlayArrow />} iconPosition="start" />
        <Tab label="خلاصه" icon={<Summarize />} iconPosition="start" />
      </Tabs>

      {/* ===== پاکسازی ===== */}
      {tab === 0 && (
        <Card><CardContent>
          <Typography fontWeight={800} mb={1}>پاکسازی انتخابی دسته‌ها</Typography>
          <Typography variant="caption" color="text.secondary" mb={2} sx={{ display: 'block' }}>
            ادمین همیشه محفوظ است. انتخاب نکنید = همهٔ دسته‌ها پاک می‌شوند.
          </Typography>
          <Grid container spacing={1}>
            {PURGE_CATEGORIES.map((c) => (
              <Grid item key={c.key} xs={12} sm={6} md={4}>
                <FormControlLabel
                  control={<Checkbox size="small" checked={purgeSel.includes(c.key)}
                    onChange={(e) => setPurgeSel((p) => e.target.checked ? [...p, c.key] : p.filter((x) => x !== c.key))} />}
                  label={c.fa} />
              </Grid>
            ))}
          </Grid>
          <Stack direction="row" spacing={1} mt={2}>
            <Button variant="outlined" size="small" onClick={() => setPurgeSel(PURGE_CATEGORIES.map((c) => c.key))}>انتخاب همه</Button>
            <Button variant="outlined" size="small" onClick={() => setPurgeSel([])}>هیچ‌کدام</Button>
            <Button variant="contained" color="error" startIcon={<Delete />}
              disabled={purgeSel.length === 0 || doPurge.isPending}
              onClick={() => setConfirmPurge(true)}>
              پاکسازی {purgeSel.length} دسته
            </Button>
          </Stack>
        </CardContent></Card>
      )}

      {/* ===== افزودن دستی ===== */}
      {tab === 1 && (
        <Stack spacing={2}>
          <Card><CardContent>
            <Typography fontWeight={800} mb={1.5}>واحد جدید</Typography>
            <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap alignItems="center">
              <TextField size="small" label="شماره واحد" value={unitNumber} sx={{ width: 150 }}
                onChange={(e) => setUnitNumber(e.target.value)} />
              <TextField size="small" type="number" label="طبقه" value={String(unitFloor)} sx={{ width: 100 }}
                onChange={(e) => setUnitFloor(Number(e.target.value) || 1)} />
              <Button variant="contained" disabled={!unitNumber} onClick={() => addUnit.mutate()}>ذخیره</Button>
            </Stack>
          </CardContent></Card>

          <Card><CardContent>
            <Typography fontWeight={800} mb={1.5}>ساکن جدید</Typography>
            <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap alignItems="center">
              <TextField select size="small" label="واحد" value={resUnit} sx={{ width: 150 }}
                onChange={(e) => setResUnit(e.target.value)}>
                {(units ?? []).map((u) => <MenuItem key={u.id} value={u.id}>{u.unit_number}</MenuItem>)}
              </TextField>
              <TextField size="small" label="نام" value={resFirst} sx={{ width: 130 }}
                onChange={(e) => setResFirst(e.target.value)} />
              <TextField size="small" label="نام خانوادگی" value={resLast} sx={{ width: 150 }}
                onChange={(e) => setResLast(e.target.value)} />
              <TextField size="small" label="موبایل" value={resMobile} sx={{ width: 130 }}
                onChange={(e) => setResMobile(e.target.value)} />
              <TextField select size="small" label="نوع" value={resType} sx={{ width: 110 }}
                onChange={(e) => setResType(e.target.value)}>
                <MenuItem value="OWNER">مالک</MenuItem>
                <MenuItem value="TENANT">مستأجر</MenuItem>
              </TextField>
              <Button variant="contained" disabled={!resUnit || !resFirst || !resLast} onClick={() => addRes.mutate()}>ذخیره</Button>
            </Stack>
          </CardContent></Card>

          <Card><CardContent>
            <Typography fontWeight={800} mb={1.5}>خودروی جدید</Typography>
            <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap alignItems="center">
              <TextField size="small" label="پلاک (مثال: 12ب345ایران11)" value={vehPlate} sx={{ width: 220 }}
                onChange={(e) => setVehPlate(e.target.value)} />
              <TextField select size="small" label="ساکن" value={vehPerson} sx={{ width: 160 }}
                onChange={(e) => setVehPerson(e.target.value)}>
                {(persons ?? []).map((p) => <MenuItem key={p.id} value={p.id}>{p.first_name} {p.last_name}</MenuItem>)}
              </TextField>
              <TextField size="small" label="برند" value={vehBrand} sx={{ width: 130 }}
                onChange={(e) => setVehBrand(e.target.value)} />
              <TextField size="small" label="رنگ" value={vehColor} sx={{ width: 110 }}
                onChange={(e) => setVehColor(e.target.value)} />
              <Button variant="contained" disabled={!vehPlate} onClick={() => addVeh.mutate()}>ذخیره</Button>
            </Stack>
            <Typography variant="caption" color="text.secondary">
              مجوز ورود به‌صورت خودکار صادر می‌شود (۳۶۵ روز).
            </Typography>
          </CardContent></Card>
        </Stack>
      )}

      {/* ===== سناریوی پیش‌فرض ===== */}
      {tab === 2 && (
        <Card><CardContent>
          <Typography fontWeight={800} mb={1}>سناریوی پیش‌فرض</Typography>
          <Typography variant="body2" mb={2}>
            پاکسازی کامل (به‌جز ادمین) ← سپس:
            <br />• ۲ ساکن (علی رضایی، مریم کریمی) هر کدام یک واحد
            <br />• هر ساکن ۳ خودرو: اولی=پارکینگ خودش، دومی=متقاضی محوطه، سومی=پارکینگ دفنی
            <br />• ۲ خودروی غریبه (فعال بدون مجوز)
            <br />• ۳ قانون DRAFT (ساکن خودش / متقاضی محوطه / ناشناس → نگهبان)
          </Typography>
          <Button variant="contained" size="large" color="primary" startIcon={<PlayArrow />}
            disabled={doSetup.isPending} onClick={() => doSetup.mutate()}>
            اجرای سناریوی پیش‌فرض
          </Button>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1.5 }}>
            ⚠️ این عملیات همهٔ داده‌های فعلی (به‌جز ادمین) را حذف و سناریوی نو می‌سازد.
          </Typography>
        </CardContent></Card>
      )}

      {/* ===== خلاصه ===== */}
      {tab === 3 && (
        <Card><CardContent>
          <Stack direction="row" spacing={1} alignItems="center" mb={1.5}>
            <Summarize />
            <Typography fontWeight={800}>وضعیت فعلی داده‌ها</Typography>
            <Box flexGrow={1} />
            <Button size="small" startIcon={<Refresh />} onClick={() => invalidate()}>به‌روزرسانی</Button>
          </Stack>
          <Grid container spacing={1}>
            {Object.entries(summary ?? {}).map(([k, v]) => (
              <Grid item key={k} xs={6} sm={4} md={2.4}>
                <Box sx={{ p: 1.2, borderRadius: 2, bgcolor: '#F0F4F8', textAlign: 'center' }}>
                  <Typography variant="h6" fontWeight={900}>{v}</Typography>
                  <Typography variant="caption" color="text.secondary">{k}</Typography>
                </Box>
              </Grid>
            ))}
          </Grid>
        </CardContent></Card>
      )}

      {/* ===== دیالوگ تأیید پاکسازی ===== */}
      <Dialog open={confirmPurge} onClose={() => setConfirmPurge(false)}>
        <DialogTitle>تأیید پاکسازی</DialogTitle>
        <DialogContent>
          <Alert severity="error" variant="outlined">
            ⚠️ {purgeSel.length} دسته انتخاب شده است. این عملیات داده‌ها را برای همیشه حذف می‌کند و قابل بازگشت نیست (به‌جز از طریق پشتیبان دستی).
          </Alert>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmPurge(false)}>انصراف</Button>
          <Button variant="contained" color="error" onClick={() => { doPurge.mutate(purgeSel); setConfirmPurge(false) }}>
            حذف قطعی
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  )
}
