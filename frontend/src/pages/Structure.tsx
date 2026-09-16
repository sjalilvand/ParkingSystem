import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, Box, Button, Card, CardContent, Chip, Dialog, DialogActions, DialogContent,
  DialogTitle, IconButton, MenuItem, Stack, Tab, Tabs, TextField, Typography,
} from '@mui/material'
import { Delete, DoorFront, Edit, GroupAdd, PersonAdd } from '@mui/icons-material'
import { api, apiErrorFa } from '../api/client'
import { jalaliDisplay } from '../utils/jalali'
import PersonPhoto from '../components/PersonPhoto'

interface Tower { id: string; complex_id: string; code: string; name: string; floor_count: number; is_active: boolean }
interface Unit { id: string; tower_id: string; unit_number: string; floor_number: number; status: string; is_active: boolean }
interface Person { id: string; first_name: string; last_name: string; national_code?: string | null; mobile?: string | null; person_type: string; photo_file_id?: string | null }
interface Occupancy { id: string; person_id: string; person_name: string; occupancy_type: string; start_date: string; end_date?: string | null; is_primary: boolean; status: string }

const emptyTower = { code: '', name: '', floor_count: '10' }
const emptyUnit = { unit_number: '', floor_number: '1' }
const emptyPerson = { first_name: '', last_name: '', national_code: '', mobile: '', person_type: 'OWNER' }

export default function Structure() {
  const qc = useQueryClient()
  const [tab, setTab] = useState(0)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')

  const [towerId, setTowerId] = useState('')

  const [towerDlg, setTowerDlg] = useState<null | { id?: string }>(null)
  const [tf, setTf] = useState({ ...emptyTower })
  const [unitDlg, setUnitDlg] = useState<null | { id?: string }>(null)
  const [uf, setUf] = useState({ ...emptyUnit })
  const [personDlg, setPersonDlg] = useState<null | { id?: string }>(null)
  const [pf, setPf] = useState({ ...emptyPerson })
  const [occDlg, setOccDlg] = useState<null | { unitId: string; id?: string }>(null)
  const [of, setOf] = useState({ person_id: '', occupancy_type: 'OWNER' })

  const { data: complexes } = useQuery({ queryKey: ['complexes'], queryFn: async () => (await api.get('/complexes')).data })
  const complexId = complexes?.[0]?.id as string | undefined

  const { data: towers } = useQuery({ queryKey: ['towers'], queryFn: async () => (await api.get('/towers')).data as Tower[] })
  const activeTower = towerId || towers?.[0]?.id || ''
  const { data: units } = useQuery({
    queryKey: ['units', activeTower],
    queryFn: async () => (await api.get('/units', { params: { tower_id: activeTower || undefined } })).data as Unit[],
    enabled: !!activeTower,
  })
  const { data: persons } = useQuery({ queryKey: ['persons'], queryFn: async () => (await api.get('/persons')).data as Person[] })

  const [occUnitId, setOccUnitId] = useState('')
  const occTarget = occUnitId || units?.[0]?.id || ''
  const { data: occupancies } = useQuery({
    queryKey: ['occupancies', occTarget],
    queryFn: async () => (await api.get(`/units/${occTarget}/occupancies`)).data as Occupancy[],
    enabled: !!occTarget,
  })

  const done = (keys: string[], m: string) => {
    setErr(''); setMsg(m)
    keys.forEach((k) => qc.invalidateQueries({ queryKey: [k] }))
  }

  const saveTower = useMutation({
    mutationFn: async (e: FormEvent) => {
      e.preventDefault()
      const body = { code: tf.code, name: tf.name, floor_count: parseInt(tf.floor_count) || 0 }
      if (towerDlg?.id) return (await api.patch(`/towers/${towerDlg.id}`, { name: tf.name, floor_count: parseInt(tf.floor_count) || 0 })).data
      return (await api.post('/towers', { ...body, complex_id: complexId })).data
    },
    onSuccess: () => { setTowerDlg(null); done(['towers'], 'برج ذخیره شد') },
    onError: (e) => setErr(apiErrorFa(e)),
  })
  const delTower = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/towers/${id}`)).data,
    onSuccess: () => { setTowerId(''); done(['towers'], 'برج حذف شد') },
    onError: (e) => setErr(apiErrorFa(e)),
  })

  const saveUnit = useMutation({
    mutationFn: async (e: FormEvent) => {
      e.preventDefault()
      const body = { unit_number: uf.unit_number, floor_number: parseInt(uf.floor_number) || 0 }
      if (unitDlg?.id) return (await api.patch(`/units/${unitDlg.id}`, body)).data
      return (await api.post('/units', { ...body, tower_id: activeTower })).data
    },
    onSuccess: () => { setUnitDlg(null); done(['units'], 'واحد ذخیره شد') },
    onError: (e) => setErr(apiErrorFa(e)),
  })
  const delUnit = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/units/${id}`)).data,
    onSuccess: () => done(['units'], 'واحد حذف شد'),
    onError: (e) => setErr(apiErrorFa(e)),
  })

  const savePerson = useMutation({
    mutationFn: async (e: FormEvent) => {
      e.preventDefault()
      const body = {
        first_name: pf.first_name, last_name: pf.last_name,
        national_code: pf.national_code || null, mobile: pf.mobile || null, person_type: pf.person_type,
      }
      if (personDlg?.id) return (await api.patch(`/persons/${personDlg.id}`, body)).data
      return (await api.post('/persons', body)).data
    },
    onSuccess: () => { setPersonDlg(null); done(['persons'], 'شخص ذخیره شد') },
    onError: (e) => setErr(apiErrorFa(e)),
  })
  const delPerson = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/persons/${id}`)).data,
    onSuccess: () => done(['persons'], 'شخص حذف شد'),
    onError: (e) => setErr(apiErrorFa(e)),
  })

  const saveOcc = useMutation({
    mutationFn: async (e: FormEvent) => {
      e.preventDefault()
      if (occDlg?.id) {
        return (await api.patch(`/occupancies/${occDlg.id}`, { occupancy_type: of.occupancy_type })).data
      }
      return (await api.post(`/units/${occDlg?.unitId}/occupancies`, {
        person_id: of.person_id, occupancy_type: of.occupancy_type,
      })).data
    },
    onSuccess: () => { setOccDlg(null); done(['occupancies'], 'سکونت ذخیره شد') },
    onError: (e) => setErr(apiErrorFa(e)),
  })
  const delOcc = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/occupancies/${id}`)).data,
    onSuccess: () => done(['occupancies'], 'سکونت حذف شد'),
    onError: (e) => setErr(apiErrorFa(e)),
  })
  const closeOcc = useMutation({
    mutationFn: async (id: string) => (await api.post(`/occupancies/${id}/close`)).data,
    onSuccess: () => done(['occupancies'], 'سکونت بسته شد'),
    onError: (e) => setErr(apiErrorFa(e)),
  })

  const submit = (e: FormEvent) => { setErr(''); e.preventDefault() }
  const dlgProps = { onClose: () => { setErr('') } }

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h6" fontWeight={800}>ساختار مجتمع</Typography>
        <Button variant="contained" onClick={() => {
          setErr('')
          if (tab === 0) { setTf({ ...emptyTower }); setTowerDlg({}) }
          else if (tab === 1) { setUf({ ...emptyUnit }); setUnitDlg({}) }
          else if (tab === 2) { setPf({ ...emptyPerson }); setPersonDlg({}) }
        }}>
          {tab === 0 ? 'برج جدید' : tab === 1 ? 'واحد جدید' : 'ثبت شخص'}
        </Button>
      </Stack>

      {msg && <Alert severity="success">{msg}</Alert>}
      {err && <Alert severity="error">{err}</Alert>}

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ bgcolor: '#fff', borderRadius: 2, px: 1 }}>
        <Tab label="برج‌ها" />
        <Tab label="واحدها" />
        <Tab label="ساکنان و سکونت" />
      </Tabs>

      {tab === 0 && (
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(3, 1fr)' }, gap: 2 }}>
          {(towers ?? []).map((t) => (
            <Card key={t.id}>
              <CardContent>
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                  <Stack>
                    <Typography fontWeight={800} fontSize={17}>{t.name}</Typography>
                    <Typography variant="body2" color="text.secondary">کد: {t.code} — {t.floor_count} طبقه</Typography>
                  </Stack>
                  <Stack direction="row" spacing={0.5}>
                    <IconButton size="small" onClick={() => { setTf({ code: t.code, name: t.name, floor_count: String(t.floor_count) }); setTowerDlg({ id: t.id }) }}>
                      <Edit fontSize="small" />
                    </IconButton>
                    <IconButton size="small" color="error" onClick={() => {
                      if (window.confirm(`حذف برج «${t.name}»؟ (در صورت داشتن واحد، رد می‌شود)`)) delTower.mutate(t.id)
                    }}><Delete fontSize="small" /></IconButton>
                  </Stack>
                </Stack>
              </CardContent>
            </Card>
          ))}
          {towers?.length === 0 && <Alert severity="info">برجی ثبت نشده.</Alert>}
        </Box>
      )}

      {tab === 1 && (
        <Stack spacing={2}>
          <Stack direction="row" spacing={2} alignItems="center">
            <TextField select size="small" label="برج" value={activeTower}
              onChange={(e) => setTowerId(e.target.value)} sx={{ width: 260 }}>
              {(towers ?? []).map((t) => <MenuItem key={t.id} value={t.id}>{t.name}</MenuItem>)}
            </TextField>
          </Stack>
          <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'repeat(2, 1fr)', md: 'repeat(5, 1fr)' }, gap: 2 }}>
            {(units ?? []).map((u) => (
              <Stack alignItems="center" sx={{ bgcolor: '#fff', border: '2px solid #E3EAF2', borderRadius: 3, py: 2 }}>
                <Typography fontWeight={900} fontSize={20}>واحد {u.unit_number}</Typography>
                <Typography variant="caption" color="text.secondary">طبقه {u.floor_number}</Typography>
                <Stack direction="row" mt={1}>
                  <IconButton size="small" onClick={() => { setUf({ unit_number: u.unit_number, floor_number: String(u.floor_number) }); setUnitDlg({ id: u.id }) }}>
                    <Edit fontSize="small" />
                  </IconButton>
                  <IconButton size="small" color="error" onClick={() => {
                    if (window.confirm(`حذف واحد ${u.unit_number}؟ (در صورت داشتن سکونت/خودرو رد می‌شود)`)) delUnit.mutate(u.id)
                  }}><Delete fontSize="small" /></IconButton>
                </Stack>
              </Stack>
            ))}
          </Box>
          {units?.length === 0 && <Alert severity="info">واحدی ثبت نشده.</Alert>}
        </Stack>
      )}

      {tab === 2 && (
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1.4fr' }, gap: 2 }}>
          <Card><CardContent>
            <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1.5}>
              <Typography fontWeight={800}>اشخاص</Typography>
            </Stack>
            {(persons ?? []).map((p) => (
              <Stack key={p.id} direction="row" justifyContent="space-between" alignItems="center"
                sx={{ py: 1, borderBottom: '1px solid #EEE' }}>
                <Stack direction="row" spacing={1.5} alignItems="center">
                  <PersonPhoto personId={p.id} photoFileId={p.photo_file_id}
                    onUploaded={() => qc.invalidateQueries({ queryKey: ['persons'] })} size={40} />
                  <Stack>
                    <Typography fontWeight={700}>{p.first_name} {p.last_name}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      {p.mobile ?? '—'} — {p.person_type === 'OWNER' ? 'مالک' : p.person_type === 'TENANT' ? 'مستأجر' : p.person_type}
                    </Typography>
                  </Stack>
                </Stack>
                <Stack direction="row">
                  <IconButton size="small" onClick={() => {
                    setPf({ first_name: p.first_name, last_name: p.last_name, national_code: p.national_code ?? '', mobile: p.mobile ?? '', person_type: p.person_type })
                    setPersonDlg({ id: p.id })
                  }}><Edit fontSize="small" /></IconButton>
                  <IconButton size="small" color="error" onClick={() => {
                    if (window.confirm(`حذف «${p.first_name} ${p.last_name}»؟ (در صورت داشتن سکونت/خودرو رد می‌شود)`)) delPerson.mutate(p.id)
                  }}><Delete fontSize="small" /></IconButton>
                </Stack>
              </Stack>
            ))}
          </CardContent></Card>

          <Card><CardContent>
            <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1.5}>
              <Typography fontWeight={800}>سکونت واحدها</Typography>
              <Button size="small" variant="contained" startIcon={<GroupAdd />} disabled={!occTarget}
                onClick={() => { setOf({ person_id: '', occupancy_type: 'OWNER' }); setOccDlg({ unitId: occTarget }) }}>
                تخصیص ساکن
              </Button>
            </Stack>
            <TextField select size="small" label="واحد" value={occTarget}
              onChange={(e) => setOccUnitId(e.target.value)} fullWidth sx={{ mb: 1.5 }}>
              {(units ?? []).map((u) => <MenuItem key={u.id} value={u.id}>واحد {u.unit_number}</MenuItem>)}
            </TextField>
            {(occupancies ?? []).map((o) => (
              <Stack key={o.id} direction="row" justifyContent="space-between" alignItems="center"
                sx={{ py: 1, borderBottom: '1px solid #EEE' }}>
                <Stack>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <Typography fontWeight={700}>{o.person_name}</Typography>
                    <Chip size="small" label={o.occupancy_type === 'OWNER' ? 'مالک' : o.occupancy_type === 'TENANT' ? 'مستأجر' : o.occupancy_type} variant="outlined" />
                    {o.is_primary && <Chip size="small" color="info" label="اصلی" />}
                  </Stack>
                  <Typography variant="caption" color="text.secondary">
                    از {jalaliDisplay(o.start_date ? new Date(o.start_date).toISOString() : null)}
                    {o.end_date ? ` تا ${jalaliDisplay(new Date(o.end_date).toISOString())}` : ''}
                  </Typography>
                </Stack>
                <Stack direction="row" spacing={0.5} alignItems="center">
                  <Chip size="small" color={o.status === 'ACTIVE' ? 'success' : 'default'} label={o.status === 'ACTIVE' ? 'جاری' : 'بسته'} />
                  {o.status === 'ACTIVE' && (
                    <Button size="small" color="warning" onClick={() => closeOcc.mutate(o.id)}>بستن</Button>
                  )}
                  <IconButton size="small" onClick={() => {
                    setOf({ person_id: o.person_id, occupancy_type: o.occupancy_type })
                    setOccDlg({ unitId: occTarget, id: o.id })
                  }}><Edit fontSize="small" /></IconButton>
                  <IconButton size="small" color="error" onClick={() => {
                    if (window.confirm('حذف سکونت؟')) delOcc.mutate(o.id)
                  }}><Delete fontSize="small" /></IconButton>
                </Stack>
              </Stack>
            ))}
            {occupancies?.length === 0 && <Typography color="text.secondary" py={2}>سکونتی ثبت نشده.</Typography>}
          </CardContent></Card>
        </Box>
      )}

      {/* دیالوگ برج */}
      <Dialog open={towerDlg !== null} onClose={() => setTowerDlg(null)}>
        <DialogTitle>{towerDlg?.id ? 'ویرایش برج' : 'برج جدید'}</DialogTitle>
        <form onSubmit={(e) => { submit(e); saveTower.mutate(e) }}>
          <DialogContent>
            <TextField fullWidth label="کد" value={tf.code} margin="normal" required
              disabled={!!towerDlg?.id} onChange={(e) => setTf((p) => ({ ...p, code: e.target.value }))} />
            <TextField fullWidth label="نام برج" value={tf.name} margin="normal" required
              onChange={(e) => setTf((p) => ({ ...p, name: e.target.value }))} />
            <TextField fullWidth label="تعداد طبقات" type="number" value={tf.floor_count} margin="normal"
              onChange={(e) => setTf((p) => ({ ...p, floor_count: e.target.value }))} />
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setTowerDlg(null)}>انصراف</Button>
            <Button type="submit" variant="contained">ذخیره</Button>
          </DialogActions>
        </form>
      </Dialog>

      {/* دیالوگ واحد */}
      <Dialog open={unitDlg !== null} onClose={() => setUnitDlg(null)}>
        <DialogTitle>{unitDlg?.id ? 'ویرایش واحد' : 'واحد جدید'}</DialogTitle>
        <form onSubmit={(e) => { submit(e); saveUnit.mutate(e) }}>
          <DialogContent>
            <TextField fullWidth label="شماره واحد" value={uf.unit_number} margin="normal" required
              onChange={(e) => setUf((p) => ({ ...p, unit_number: e.target.value }))} />
            <TextField fullWidth label="طبقه" type="number" value={uf.floor_number} margin="normal"
              onChange={(e) => setUf((p) => ({ ...p, floor_number: e.target.value }))} />
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setUnitDlg(null)}>انصراف</Button>
            <Button type="submit" variant="contained">ذخیره</Button>
          </DialogActions>
        </form>
      </Dialog>

      {/* دیالوگ شخص */}
      <Dialog open={personDlg !== null} onClose={() => setPersonDlg(null)}>
        <DialogTitle>{personDlg?.id ? 'ویرایش شخص' : 'ثبت شخص'}</DialogTitle>
        <form onSubmit={(e) => { submit(e); savePerson.mutate(e) }}>
          <DialogContent>
            <TextField fullWidth label="نام" value={pf.first_name} margin="normal" required
              onChange={(e) => setPf((p) => ({ ...p, first_name: e.target.value }))} />
            <TextField fullWidth label="نام خانوادگی" value={pf.last_name} margin="normal" required
              onChange={(e) => setPf((p) => ({ ...p, last_name: e.target.value }))} />
            <TextField fullWidth label="کد ملی" value={pf.national_code} margin="normal"
              onChange={(e) => setPf((p) => ({ ...p, national_code: e.target.value }))} />
            <TextField fullWidth label="موبایل" value={pf.mobile} margin="normal"
              onChange={(e) => setPf((p) => ({ ...p, mobile: e.target.value }))} />
            <TextField fullWidth select label="نوع" value={pf.person_type} margin="normal"
              onChange={(e) => setPf((p) => ({ ...p, person_type: e.target.value }))}>
              <MenuItem value="OWNER">مالک</MenuItem>
              <MenuItem value="TENANT">مستأجر</MenuItem>
              <MenuItem value="STAFF">کارمند</MenuItem>
            </TextField>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setPersonDlg(null)}>انصراف</Button>
            <Button type="submit" variant="contained">ذخیره</Button>
          </DialogActions>
        </form>
      </Dialog>

      {/* دیالوگ سکونت */}
      <Dialog open={occDlg !== null} onClose={() => setOccDlg(null)}>
        <DialogTitle>{occDlg?.id ? 'ویرایش سکونت' : 'تخصیص ساکن'}</DialogTitle>
        <form onSubmit={(e) => { submit(e); saveOcc.mutate(e) }}>
          <DialogContent>
            {occDlg?.id ? (
              <Typography variant="body2" color="text.secondary" mb={1}>نوع سکونت را تغییر دهید:</Typography>
            ) : (
              <TextField fullWidth select label="شخص" value={of.person_id} margin="normal" required
                onChange={(e) => setOf((p) => ({ ...p, person_id: e.target.value }))}>
                {(persons ?? []).map((p) => (
                  <MenuItem key={p.id} value={p.id}>{p.first_name} {p.last_name}</MenuItem>
                ))}
              </TextField>
            )}
            <TextField fullWidth select label="نوع سکونت" value={of.occupancy_type} margin="normal"
              onChange={(e) => setOf((p) => ({ ...p, occupancy_type: e.target.value }))}>
              <MenuItem value="OWNER">مالک</MenuItem>
              <MenuItem value="TENANT">مستأجر</MenuItem>
              <MenuItem value="GUEST">مهمان</MenuItem>
            </TextField>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setOccDlg(null)}>انصراف</Button>
            <Button type="submit" variant="contained"
              disabled={!occDlg?.id && !of.person_id}>ذخیره</Button>
          </DialogActions>
        </form>
      </Dialog>
    </Stack>
  )
}