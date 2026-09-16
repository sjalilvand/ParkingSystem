import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  IconButton,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from '@mui/material'
import { PersonAdd, Delete } from '@mui/icons-material'
import { api, apiErrorFa } from '../api/client'
import PersonPhoto from '../components/PersonPhoto'
import { faDate } from '../utils/format'

interface Brand { id: string; name_fa: string; name_en?: string | null; country: string }
interface VColor { id: string; name_fa: string; hex_code: string }
interface Person { id: string; first_name: string; last_name: string; mobile?: string | null; person_type: string; photo_file_id?: string | null }

export default function BaseData() {
  const qc = useQueryClient()
  const [tab, setTab] = useState(0)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')

  const [newBrand, setNewBrand] = useState({ name_fa: '', name_en: '', country: 'IR' })
  const [newColor, setNewColor] = useState({ name_fa: '', hex_code: '#9E9E9E' })
  const [newPerson, setNewPerson] = useState({ first_name: '', last_name: '', mobile: '', national_code: '' })

  const done = (k: string, m: string) => {
    setErr(''); setMsg(m); qc.invalidateQueries({ queryKey: [k] })
  }

  const { data: brands } = useQuery({ queryKey: ['brands'], queryFn: async () => (await api.get('/base-data/brands')).data as Brand[] })
  const { data: colors } = useQuery({ queryKey: ['colors'], queryFn: async () => (await api.get('/base-data/colors')).data as VColor[] })
  const { data: persons } = useQuery({ queryKey: ['persons'], queryFn: async () => (await api.get('/persons')).data as Person[] })

  const addBrand = useMutation({
    mutationFn: async () => (await api.post('/base-data/brands', newBrand)).data,
    onSuccess: () => { setNewBrand({ name_fa: '', name_en: '', country: 'IR' }); done('brands', 'برند اضافه شد') },
    onError: (e) => setErr(apiErrorFa(e)),
  })
  const delBrand = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/base-data/brands/${id}`)).data,
    onSuccess: () => done('brands', 'برند حذف شد'),
    onError: (e) => setErr(apiErrorFa(e)),
  })
  const addColor = useMutation({
    mutationFn: async () => (await api.post('/base-data/colors', newColor)).data,
    onSuccess: () => { setNewColor({ name_fa: '', hex_code: '#9E9E9E' }); done('colors', 'رنگ اضافه شد') },
    onError: (e) => setErr(apiErrorFa(e)),
  })
  const delColor = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/base-data/colors/${id}`)).data,
    onSuccess: () => done('colors', 'رنگ حذف شد'),
    onError: (e) => setErr(apiErrorFa(e)),
  })
  const addPerson = useMutation({
    mutationFn: async () => (await api.post('/persons', {
      first_name: newPerson.first_name, last_name: newPerson.last_name,
      mobile: newPerson.mobile || null, national_code: newPerson.national_code || null,
    })).data,
    onSuccess: () => { setNewPerson({ first_name: '', last_name: '', mobile: '', national_code: '' }); done('persons', 'شخص ثبت شد') },
    onError: (e) => setErr(apiErrorFa(e)),
  })

  return (
    <Stack spacing={2}>
      <Typography variant="h6" fontWeight={800}>اطلاعات پایه</Typography>
      {err && <Alert severity="error">{err}</Alert>}
      {msg && <Alert severity="success">{msg}</Alert>}

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ bgcolor: '#fff', borderRadius: 2, px: 1 }}>
        <Tab label="برندها" />
        <Tab label="رنگ‌ها" />
        <Tab label="اشخاص و عکس" />
      </Tabs>

      {tab === 0 && (
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 2fr' }, gap: 2 }}>
          <Card><CardContent>
            <Typography fontWeight={800} mb={1.5}>برند جدید</Typography>
            <TextField fullWidth size="small" label="نام فارسی" value={newBrand.name_fa}
              onChange={(e) => setNewBrand((p) => ({ ...p, name_fa: e.target.value }))} sx={{ mb: 1.5 }} />
            <TextField fullWidth size="small" label="نام انگلیسی (اختیاری)" value={newBrand.name_en}
              onChange={(e) => setNewBrand((p) => ({ ...p, name_en: e.target.value }))} sx={{ mb: 1.5 }} />
            <TextField fullWidth size="small" select label="نوع" value={newBrand.country}
              onChange={(e) => setNewBrand((p) => ({ ...p, country: e.target.value }))} sx={{ mb: 1.5 }}
              SelectProps={{ native: true }}>
              <option value="IR">ایرانی</option>
              <option value="IMPORT">وارداتی</option>
            </TextField>
            <Button fullWidth variant="contained" onClick={() => addBrand.mutate()} disabled={!newBrand.name_fa.trim()}>
              افزودن برند
            </Button>
          </CardContent></Card>
          <Card><CardContent>
            <Typography fontWeight={800} mb={1}>فهرست برندها ({brands?.length ?? 0})</Typography>
            <Box sx={{ maxHeight: 420, overflow: 'auto' }}>
              {(brands ?? []).map((b) => (
                <Stack key={b.id} direction="row" justifyContent="space-between" alignItems="center"
                  sx={{ py: 0.8, borderBottom: '1px solid #EEE' }}>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <Chip size="small" color={b.country === 'IR' ? 'primary' : 'default'}
                      label={b.country === 'IR' ? 'ایرانی' : 'وارداتی'} />
                    <Typography>{b.name_fa}</Typography>
                    <Typography variant="caption" color="text.secondary">{b.name_en ?? ''}</Typography>
                  </Stack>
                  <IconButton size="small" color="error" onClick={() => delBrand.mutate(b.id)}><Delete /></IconButton>
                </Stack>
              ))}
            </Box>
          </CardContent></Card>
        </Box>
      )}

      {tab === 1 && (
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 2fr' }, gap: 2 }}>
          <Card><CardContent>
            <Typography fontWeight={800} mb={1.5}>رنگ جدید</Typography>
            <Stack direction="row" spacing={1} alignItems="center" mb={1.5}>
              <Box sx={{ width: 40, height: 40, borderRadius: '50%', bgcolor: newColor.hex_code, border: '1px solid #B0BEC5' }} />
              <TextField fullWidth size="small" label="نام رنگ" value={newColor.name_fa}
                onChange={(e) => setNewColor((p) => ({ ...p, name_fa: e.target.value }))} />
              <TextField size="small" label="کد" sx={{ width: 130 }} value={newColor.hex_code}
                onChange={(e) => setNewColor((p) => ({ ...p, hex_code: e.target.value }))} />
            </Stack>
            <Button fullWidth variant="contained" onClick={() => addColor.mutate()} disabled={!newColor.name_fa.trim()}>
              افزودن رنگ
            </Button>
          </CardContent></Card>
          <Card><CardContent>
            <Typography fontWeight={800} mb={1}>فهرست رنگ‌ها ({colors?.length ?? 0})</Typography>
            <Box sx={{ maxHeight: 420, overflow: 'auto' }}>
              {(colors ?? []).map((c) => (
                <Stack key={c.id} direction="row" justifyContent="space-between" alignItems="center"
                  sx={{ py: 0.8, borderBottom: '1px solid #EEE' }}>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <Box sx={{ width: 18, height: 18, borderRadius: '50%', bgcolor: c.hex_code, border: '1px solid #B0BEC5' }} />
                    <Typography>{c.name_fa}</Typography>
                    <Typography variant="caption" color="text.secondary">{c.hex_code}</Typography>
                  </Stack>
                  <IconButton size="small" color="error" onClick={() => delColor.mutate(c.id)}><Delete /></IconButton>
                </Stack>
              ))}
            </Box>
          </CardContent></Card>
        </Box>
      )}

      {tab === 2 && (
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 2fr' }, gap: 2 }}>
          <Card><CardContent>
            <Stack direction="row" spacing={1} alignItems="center" mb={1.5}>
              <PersonAdd color="primary" />
              <Typography fontWeight={800}>شخص جدید</Typography>
            </Stack>
            <TextField fullWidth size="small" label="نام" value={newPerson.first_name}
              onChange={(e) => setNewPerson((p) => ({ ...p, first_name: e.target.value }))} sx={{ mb: 1.5 }} />
            <TextField fullWidth size="small" label="نام خانوادگی" value={newPerson.last_name}
              onChange={(e) => setNewPerson((p) => ({ ...p, last_name: e.target.value }))} sx={{ mb: 1.5 }} />
            <TextField fullWidth size="small" label="کد ملی (اختیاری)" value={newPerson.national_code}
              onChange={(e) => setNewPerson((p) => ({ ...p, national_code: e.target.value }))} sx={{ mb: 1.5 }} />
            <TextField fullWidth size="small" label="موبایل (اختیاری)" value={newPerson.mobile}
              onChange={(e) => setNewPerson((p) => ({ ...p, mobile: e.target.value }))} sx={{ mb: 1.5 }} />
            <Button fullWidth variant="contained" onClick={() => addPerson.mutate()}
              disabled={!newPerson.first_name.trim() || !newPerson.last_name.trim()}>
              ثبت شخص
            </Button>
          </CardContent></Card>
          <Card><CardContent>
            <Typography fontWeight={800} mb={1}>
              اشخاص — برای هر شخص می‌توانید عکس بارگذاری کنید ({persons?.length ?? 0})
            </Typography>
            <Box sx={{ maxHeight: 420, overflow: 'auto' }}>
              {(persons ?? []).map((p) => (
                <Stack key={p.id} direction="row" justifyContent="space-between" alignItems="center"
                  sx={{ py: 1, borderBottom: '1px solid #EEE' }}>
                  <Stack direction="row" spacing={1.5} alignItems="center">
                    <PersonPhoto personId={p.id} photoFileId={p.photo_file_id}
                      onUploaded={() => qc.invalidateQueries({ queryKey: ['persons'] })} />
                    <Stack>
                      <Typography fontWeight={700}>{p.first_name} {p.last_name}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {p.mobile ?? '—'} — {faDate(null as unknown as string)}
                      </Typography>
                    </Stack>
                  </Stack>
                  <Chip size="small" label={p.person_type === 'OWNER' ? 'مالک' : p.person_type === 'TENANT' ? 'مستأجر' : p.person_type} />
                </Stack>
              ))}
            </Box>
          </CardContent></Card>
        </Box>
      )}
    </Stack>
  )
}