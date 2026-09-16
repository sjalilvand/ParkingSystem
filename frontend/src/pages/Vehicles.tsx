import { useMemo, useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, Box, Button, Card, CardContent, Chip, Dialog, DialogActions, DialogContent,
  DialogTitle, IconButton, MenuItem, Stack, TextField, Typography,
} from '@mui/material'
import { Add, Delete, Edit, LocationOn, RemoveCircleOutline, TaskAlt } from '@mui/icons-material'
import { api, apiErrorFa } from '../api/client'
import { faDate } from '../utils/format'
import PlateBox from '../components/PlateBox'
import PlateInput, { parsePlateRaw } from '../components/PlateInput'

interface Brand { id: string; name_fa: string; country: string; is_active: boolean }
interface VColor { id: string; name_fa: string; hex_code: string; is_active: boolean }
interface Person { id: string; first_name: string; last_name: string }
interface Unit { id: string; tower_id: string; unit_number: string }
interface Tower { id: string; name: string }
interface Region { id: string; plate_code: string; province: string; city: string; letters?: string | null }
interface VehicleRow {
  id: string; plate_raw: string; plate_normalized: string
  brand?: string | null; model?: string | null; color?: string | null; year?: number | null
  owner_person_id?: string | null; unit_id?: string | null
  owner_name?: string | null; unit_number?: string | null; tower_name?: string | null
  plate_province?: string | null; plate_city?: string | null
  is_active: boolean; notes?: string | null
}

const emptyForm = {
  plate: '', brand: '', model: '', color: '', year: '',
  owner_person_id: '', unit_id: '', notes: '',
}

export default function Vehicles() {
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')

  const [dialog, setDialog] = useState(false)
  const [editId, setEditId] = useState<string | null>(null)
  const [f, setF] = useState({ ...emptyForm })

  const [brandMgmt, setBrandMgmt] = useState(false)
  const [newBrand, setNewBrand] = useState({ name_fa: '', country: 'IR' })
  const [colorMgmt, setColorMgmt] = useState(false)
  const [newColor, setNewColor] = useState({ name_fa: '', hex_code: '#9E9E9E' })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['vehicles'] })
    qc.invalidateQueries({ queryKey: ['brands'] })
    qc.invalidateQueries({ queryKey: ['colors'] })
  }

  const { data } = useQuery({
    queryKey: ['vehicles', search],
    queryFn: async () => (await api.get('/vehicles', { params: { search: search || undefined, page_size: 100 } })).data,
  })
  const { data: brands } = useQuery({ queryKey: ['brands'], queryFn: async () => (await api.get('/base-data/brands')).data as Brand[] })
  const { data: colors } = useQuery({ queryKey: ['colors'], queryFn: async () => (await api.get('/base-data/colors')).data as VColor[] })
  const { data: persons } = useQuery({ queryKey: ['persons'], queryFn: async () => (await api.get('/persons')).data as Person[] })
  const { data: towers } = useQuery({ queryKey: ['towers'], queryFn: async () => (await api.get('/towers')).data as Tower[] })
  const { data: regions } = useQuery({ queryKey: ['plate-regions'], queryFn: async () => (await api.get('/base-data/plate-regions')).data as Region[] })

  const [towerId, setTowerId] = useState('')
  const activeTower = towerId || towers?.[0]?.id || ''
  const { data: units } = useQuery({
    queryKey: ['units', activeTower],
    queryFn: async () => (await api.get('/units', { params: { tower_id: activeTower || undefined } })).data as Unit[],
    enabled: !!activeTower,
  })

  const colorHex = (name?: string | null) => (colors ?? []).find((c) => c.name_fa === name)?.hex_code

  // resolve زنده استان/شهر از فرم
  const parsed = useMemo(() => parsePlateRaw(f.plate), [f.plate])
  const regionInfo = useMemo(() => {
    if (!parsed.letterFa || (!parsed.province && !parsed.two)) return null
    const fa2en = (s: string) => s.replace(/[۰-۹]/g, (d) => String(d.charCodeAt(0) & 15))
    const codeEn = fa2en(parsed.province) || fa2en(parsed.two)
    const rows = (regions ?? []).filter((r) => r.plate_code === codeEn)
    const normL = (s: string) => s.replace(/\u0640/g, '').replace(/ك/g, 'ک').replace(/[يى]/g, 'ی').trim()
    const hit = rows.find((r) => (r.letters || '').split(/\s+/).map(normL).includes(normL(parsed.letterFa)))
    if (hit) return { province: hit.province, city: hit.city }
    return rows.length ? { province: rows[0].province, city: null } : null
  }, [parsed, regions])

  const openCreate = () => { setEditId(null); setF({ ...emptyForm }); setErr(''); setDialog(true) }
  const openEdit = (v: VehicleRow) => {
    setEditId(v.id)
    setF({
      plate: v.plate_raw ?? '', brand: v.brand ?? '', model: v.model ?? '',
      color: v.color ?? '', year: v.year ? String(v.year) : '',
      owner_person_id: v.owner_person_id ?? '', unit_id: v.unit_id ?? '', notes: v.notes ?? '',
    })
    setErr(''); setDialog(true)
  }

  const save = useMutation({
    mutationFn: async (e: FormEvent) => {
      e.preventDefault()
      const payload: Record<string, unknown> = {
        plate_raw: f.plate, brand: f.brand || null, model: f.model || null,
        color: f.color || null, year: f.year ? parseInt(f.year) : null,
        owner_person_id: f.owner_person_id || null, unit_id: f.unit_id || null,
        notes: f.notes || null,
      }
      if (parsed.letterFa) payload.plate_letter = parsed.letterFa
      const effCode = parsed.province || parsed.two
      if (effCode) payload.plate_province_code = effCode
      if (editId) return (await api.patch(`/vehicles/${editId}`, payload)).data
      return (await api.post('/vehicles', payload)).data
    },
    onSuccess: () => {
      setDialog(false); setErr(''); setMsg(editId ? 'خودرو ویرایش شد' : 'خودرو ثبت شد')
      invalidate()
    },
    onError: (e) => setErr(apiErrorFa(e)),
  })

  const toggleActive = useMutation({
    mutationFn: async (p: { id: string; act: 'activate' | 'deactivate' }) =>
      (await api.post(`/vehicles/${p.id}/${p.act}`)).data,
    onSuccess: () => { setErr(''); invalidate() },
    onError: (e) => setErr(apiErrorFa(e)),
  })

  const addBrand = useMutation({
    mutationFn: async () => (await api.post('/base-data/brands', newBrand)).data,
    onSuccess: () => { setNewBrand({ name_fa: '', country: 'IR' }); invalidate() },
    onError: (e) => setErr(apiErrorFa(e)),
  })
  const delBrand = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/base-data/brands/${id}`)).data,
    onSuccess: () => invalidate(),
    onError: (e) => setErr(apiErrorFa(e)),
  })
  const addColor = useMutation({
    mutationFn: async () => (await api.post('/base-data/colors', newColor)).data,
    onSuccess: () => { setNewColor({ name_fa: '', hex_code: '#9E9E9E' }); invalidate() },
    onError: (e) => setErr(apiErrorFa(e)),
  })
  const delColor = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/base-data/colors/${id}`)).data,
    onSuccess: () => invalidate(),
    onError: (e) => setErr(apiErrorFa(e)),
  })

  const submit = (e: FormEvent) => { setErr(''); save.mutate(e) }

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
        <Typography variant="h6" fontWeight={800}>خودروها</Typography>
        <Stack direction="row" spacing={1}>
          <Button variant="outlined" onClick={() => setBrandMgmt(true)}>مدیریت برندها</Button>
          <Button variant="outlined" onClick={() => setColorMgmt(true)}>مدیریت رنگ‌ها</Button>
          <Button variant="contained" onClick={openCreate}>ثبت خودرو جدید</Button>
        </Stack>
      </Stack>

      {msg && <Alert severity="success">{msg}</Alert>}
      {err && <Alert severity="error">{err}</Alert>}

      <TextField size="small" placeholder="جستجو (پلاک / برند / رنگ / استان / شهر)"
        value={search} onChange={(e) => setSearch(e.target.value)} sx={{ width: 380 }} />

      {(data?.items ?? []).map((v: VehicleRow) => (
        <Card key={v.id}>
          <CardContent sx={{ py: 2 }}>
            <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={2}>
              <Stack spacing={1} alignItems="flex-start">
                <PlateBox plate={v.plate_raw || v.plate_normalized} />
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  {v.brand && <Chip size="small" label={v.brand} variant="outlined" />}
                  {v.model && <Chip size="small" label={`مدل ${v.model}`} variant="outlined" />}
                  {v.color && colorHex(v.color) && (
                    <Chip size="small" variant="outlined" label={v.color}
                      icon={<Box sx={{ width: 12, height: 12, borderRadius: '50%', bgcolor: colorHex(v.color), ml: 0.5 }} />} />
                  )}
                  {v.year && <Chip size="small" label={`سال ${v.year}`} variant="outlined" />}
                </Stack>
                <Stack direction="row" spacing={0.5} alignItems="center">
                  <LocationOn fontSize="small" color="primary" />
                  <Typography variant="caption" color="text.secondary">
                    {v.plate_province
                      ? `${v.plate_province}${v.plate_city ? ` — ${v.plate_city}` : ''}`
                      : 'استان/شهر نامشخص'}
                    {' — مالک: '}{v.owner_name ?? '—'}
                    {v.unit_number ? ` — واحد ${v.unit_number}${v.tower_name ? ` (${v.tower_name})` : ''}` : ''}
                    {' — '}{faDate(v.created_at as string)}
                  </Typography>
                </Stack>
              </Stack>
              <Stack direction="row" spacing={1} alignItems="center">
                <Chip size="small" color={v.is_active ? 'success' : 'default'}
                  icon={v.is_active ? <TaskAlt /> : <RemoveCircleOutline />}
                  label={v.is_active ? 'فعال' : 'غیرفعال'} />
                <IconButton size="small" color="primary" onClick={() => openEdit(v)}><Edit /></IconButton>
                {v.is_active ? (
                  <Button size="small" color="warning"
                    onClick={() => toggleActive.mutate({ id: v.id, act: 'deactivate' })}>غیرفعال</Button>
                ) : (
                  <Button size="small" color="success"
                    onClick={() => toggleActive.mutate({ id: v.id, act: 'activate' })}>فعال</Button>
                )}
              </Stack>
            </Stack>
          </CardContent>
        </Card>
      ))}
      {data?.items?.length === 0 && <Alert severity="info">خودرویی یافت نشد.</Alert>}

      {/* دیالوگ ثبت/ویرایش */}
      <Dialog open={dialog} onClose={() => setDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{editId ? 'ویرایش خودرو' : 'ثبت خودرو جدید'}</DialogTitle>
        <form onSubmit={submit}>
          <DialogContent>
            {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}
            <PlateInput raw={f.plate} onChange={(raw) => setF((p) => ({ ...p, plate: raw }))} />
            {f.plate.trim() ? (
              <Stack spacing={1} alignItems="center" my={1.5}>
                <PlateBox plate={f.plate} />
                {regionInfo ? (
                  <Chip icon={<LocationOn />} size="small" color="info"
                    label={`استان: ${regionInfo.province}${regionInfo.city ? ` — شهرستان: ${regionInfo.city}` : ''} (خودکار)`} />
                ) : (
                  <Chip size="small" color="warning" label="ترکیب کد استان + حرف در جدول پایه یافت نشد" />
                )}
              </Stack>
            ) : null}

            <Stack direction="row" spacing={1}>
              <TextField fullWidth select label="برند" value={f.brand}
                onChange={(e) => setF((p) => ({ ...p, brand: e.target.value }))}>
                <MenuItem value="">—</MenuItem>
                {(brands ?? []).filter((b) => b.is_active).map((b) => (
                  <MenuItem key={b.id} value={b.name_fa}>
                    {b.name_fa} {b.country === 'IR' ? '(ایرانی)' : ''}
                  </MenuItem>
                ))}
              </TextField>
              <TextField fullWidth label="مدل" value={f.model}
                onChange={(e) => setF((p) => ({ ...p, model: e.target.value }))} />
            </Stack>

            <Stack direction="row" spacing={1} mt={2}>
              <TextField fullWidth select label="رنگ" value={f.color}
                onChange={(e) => setF((p) => ({ ...p, color: e.target.value }))}>
                <MenuItem value="">—</MenuItem>
                {(colors ?? []).filter((c) => c.is_active).map((c) => (
                  <MenuItem key={c.id} value={c.name_fa}>
                    <Stack direction="row" spacing={1} alignItems="center">
                      <Box sx={{ width: 14, height: 14, borderRadius: '50%', bgcolor: c.hex_code, border: '1px solid #B0BEC5' }} />
                      {c.name_fa}
                    </Stack>
                  </MenuItem>
                ))}
              </TextField>
              <TextField fullWidth label="سال ساخت" type="number" value={f.year}
                onChange={(e) => setF((p) => ({ ...p, year: e.target.value.replace(/[^0-9۰-۹]/g, '').replace(/[۰-۹]/g, (d) => String(d.charCodeAt(0) & 15)).slice(0, 4) }))} />
            </Stack>

            <Stack direction="row" spacing={1} mt={2}>
              <TextField fullWidth select label="مالک" value={f.owner_person_id}
                onChange={(e) => setF((p) => ({ ...p, owner_person_id: e.target.value }))}>
                <MenuItem value="">—</MenuItem>
                {(persons ?? []).map((p) => (
                  <MenuItem key={p.id} value={p.id}>{p.first_name} {p.last_name}</MenuItem>
                ))}
              </TextField>
              <TextField fullWidth select label="واحد مسکونی" value={f.unit_id}
                onChange={(e) => setF((p) => ({ ...p, unit_id: e.target.value }))}>
                <MenuItem value="">—</MenuItem>
                {(units ?? []).map((u) => <MenuItem key={u.id} value={u.id}>واحد {u.unit_number}</MenuItem>)}
              </TextField>
            </Stack>
            <TextField fullWidth select label="برج (برای فهرست واحدها)" value={activeTower}
              onChange={(e) => setTowerId(e.target.value)} sx={{ mt: 2 }}>
              {(towers ?? []).map((t) => <MenuItem key={t.id} value={t.id}>{t.name}</MenuItem>)}
            </TextField>

            <TextField fullWidth label="توضیحات" value={f.notes} multiline rows={2}
              onChange={(e) => setF((p) => ({ ...p, notes: e.target.value }))} sx={{ mt: 2 }} />
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setDialog(false)}>انصراف</Button>
            <Button type="submit" variant="contained" disabled={save.isPending}>
              {editId ? 'ذخیره تغییرات' : 'ثبت'}
            </Button>
          </DialogActions>
        </form>
      </Dialog>

      {/* مدیریت برندها */}
      <Dialog open={brandMgmt} onClose={() => setBrandMgmt(false)} maxWidth="sm" fullWidth>
        <DialogTitle>مدیریت برندها</DialogTitle>
        <DialogContent>
          <Stack direction="row" spacing={1} mt={1} mb={2}>
            <TextField size="small" fullWidth label="نام برند (فارسی)" value={newBrand.name_fa}
              onChange={(e) => setNewBrand((p) => ({ ...p, name_fa: e.target.value }))} />
            <TextField size="small" select label="نوع" sx={{ width: 140 }} value={newBrand.country}
              onChange={(e) => setNewBrand((p) => ({ ...p, country: e.target.value }))}>
              <MenuItem value="IR">ایرانی</MenuItem>
              <MenuItem value="IMPORT">وارداتی</MenuItem>
            </TextField>
            <IconButton color="primary" onClick={() => addBrand.mutate()} disabled={!newBrand.name_fa.trim()}><Add /></IconButton>
          </Stack>
          {(brands ?? []).map((b) => (
            <Stack key={b.id} direction="row" justifyContent="space-between" alignItems="center"
              sx={{ py: 0.8, borderBottom: '1px solid #EEE' }}>
              <Stack direction="row" spacing={1} alignItems="center">
                <Chip size="small" color={b.country === 'IR' ? 'primary' : 'default'}
                  label={b.country === 'IR' ? 'ایرانی' : 'وارداتی'} />
                <Typography>{b.name_fa}</Typography>
              </Stack>
              <IconButton size="small" color="error" onClick={() => delBrand.mutate(b.id)}><Delete /></IconButton>
            </Stack>
          ))}
        </DialogContent>
        <DialogActions><Button onClick={() => setBrandMgmt(false)}>بستن</Button></DialogActions>
      </Dialog>

      {/* مدیریت رنگ‌ها */}
      <Dialog open={colorMgmt} onClose={() => setColorMgmt(false)} maxWidth="sm" fullWidth>
        <DialogTitle>مدیریت رنگ‌ها</DialogTitle>
        <DialogContent>
          <Stack direction="row" spacing={1} mt={1} mb={2} alignItems="center">
            <Box sx={{ width: 36, height: 36, borderRadius: '50%', bgcolor: newColor.hex_code, border: '1px solid #B0BEC5' }} />
            <TextField size="small" fullWidth label="نام رنگ" value={newColor.name_fa}
              onChange={(e) => setNewColor((p) => ({ ...p, name_fa: e.target.value }))} />
            <TextField size="small" label="کد" sx={{ width: 130 }} value={newColor.hex_code}
              onChange={(e) => setNewColor((p) => ({ ...p, hex_code: e.target.value }))} />
            <IconButton color="primary" onClick={() => addColor.mutate()} disabled={!newColor.name_fa.trim()}><Add /></IconButton>
          </Stack>
          {(colors ?? []).map((c) => (
            <Stack key={c.id} direction="row" justifyContent="space-between" alignItems="center"
              sx={{ py: 0.8, borderBottom: '1px solid #EEE' }}>
              <Stack direction="row" spacing={1} alignItems="center">
                <Box sx={{ width: 18, height: 18, borderRadius: '50%', bgcolor: c.hex_code, border: '1px solid #B0BEC5' }} />
                <Typography>{c.name_fa}</Typography>
              </Stack>
              <IconButton size="small" color="error" onClick={() => delColor.mutate(c.id)}><Delete /></IconButton>
            </Stack>
          ))}
        </DialogContent>
        <DialogActions><Button onClick={() => setColorMgmt(false)}>بستن</Button></DialogActions>
      </Dialog>
    </Stack>
  )
}