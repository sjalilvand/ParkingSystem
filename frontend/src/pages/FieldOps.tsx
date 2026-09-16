import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Alert, Box, Button, Card, CardContent, Chip, MenuItem, Stack, TextField, Typography,
} from '@mui/material'
import { CloudDone, CloudOff, DeleteForever, PhotoCamera, Refresh, Search, Tour } from '@mui/icons-material'
import { api, apiErrorFa } from '../api/client'
import { useOfflineSync } from '../offline/sync'
import { offlineDB, type PendingViolation } from '../offline/db'
import PlateBox from '../components/PlateBox'
import { faDate, money } from '../utils/format'

interface VType { id: string; code: string; title: string; default_penalty_amount: number }
interface Present { id: string; plate_normalized: string; entry_at: string; duration_seconds: number }

export default function FieldOps() {
  const { online, syncing, lastMsg, syncNow } = useOfflineSync()
  const [queue, setQueue] = useState<PendingViolation[]>([])
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const [plate, setPlate] = useState('')
  const [vtype, setVtype] = useState('')
  const [desc, setDesc] = useState('')
  const [photo, setPhoto] = useState<string | null>(null)
  const [photoName, setPhotoName] = useState('')

  const [searchPlate, setSearchPlate] = useState('')
  const [searchResult, setSearchResult] = useState<{ found?: boolean; data?: Record<string, unknown> } | null>(null)

  const refreshQueue = useCallback(async () => {
    const items = await offlineDB.pending_violations.orderBy('created_at').reverse().toArray()
    setQueue(items)
  }, [])

  useEffect(() => { refreshQueue() }, [refreshQueue])
  useEffect(() => {
    const iv = setInterval(refreshQueue, 5000)
    return () => clearInterval(iv)
  }, [refreshQueue])

  const { data: serverTypes } = useQuery({
    queryKey: ['violation-types'],
    queryFn: async () => (await api.get('/violations/types')).data as VType[],
    enabled: online,
  })
  const [cachedTypes, setCachedTypes] = useState<VType[]>([])
  useEffect(() => {
    if (serverTypes && serverTypes.length > 0) {
      offlineDB.kv.put({ key: 'violation_types', value: serverTypes })
      setCachedTypes(serverTypes)
      setVtype((cur) => cur || serverTypes[0]?.code || '')
    }
  }, [serverTypes])
  useEffect(() => {
    offlineDB.kv.get('violation_types').then((v) => {
      if (v && v.value) {
        const cached = v.value as VType[]
        setCachedTypes(cached)
        setVtype((cur) => cur || cached[0]?.code || '')
      }
    })
  }, [])
  const effectiveTypes = (online && serverTypes && serverTypes.length > 0) ? serverTypes : cachedTypes

  const { data: present } = useQuery({
    queryKey: ['current-vehicles'],
    queryFn: async () => (await api.get('/reports/current-vehicles')).data as Present[],
    enabled: online,
    refetchInterval: 20000,
  })

  const onPhotoPick = (file: File | null) => {
    if (!file) { setPhoto(null); setPhotoName(''); return }
    if (file.size > 8 * 1024 * 1024) { setErr('حجم عکس باید کمتر از ۸ مگابایت باشد'); return }
    const reader = new FileReader()
    reader.onload = () => { setPhoto(String(reader.result)); setPhotoName(file.name) }
    reader.readAsDataURL(file)
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setErr(''); setMsg('')
    if (!plate.trim() || !vtype) { setErr('پلاک و نوع تخلف الزامی است'); return }
    const clientRef = crypto.randomUUID()
    await offlineDB.pending_violations.add({
      client_ref: clientRef,
      plate: plate.trim(),
      type_code: vtype,
      description: desc || undefined,
      photo_data: photo || undefined,
      created_at: new Date().toISOString(),
      tries: 0,
      status: 'pending',
    })
    setPlate(''); setDesc(''); setPhoto(null); setPhotoName('')
    await refreshQueue()
    if (online) {
      setMsg('در صف ثبت شد — در حال همگام‌سازی...')
      await syncNow()
      await refreshQueue()
    } else {
      setMsg('آفلاین — تخلف و عکس در صف ذخیره شد و بعد از وصل‌شدن شبکه ارسال می‌شود')
    }
  }

  const deleteItem = async (ref: string) => {
    await offlineDB.pending_violations.delete(ref)
    await refreshQueue()
  }

  const doSearch = async () => {
    setErr(''); setSearchResult(null)
    if (!searchPlate.trim()) return
    try {
      const r = await api.get(`/vehicles/by-plate/${encodeURIComponent(searchPlate.trim())}`)
      setSearchResult({ found: true, data: r.data })
    } catch (e) {
      const status = (e as { response?: { status?: number } })?.response?.status
      if (status === 404) setSearchResult({ found: false })
      else setErr(apiErrorFa(e))
    }
  }

  const pendingCount = queue.filter((q) => q.status === 'pending').length
  const errorCount = queue.filter((q) => q.status === 'error').length

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Tour color="primary" />
          <Typography variant="h6" fontWeight={800}>پنل مسئول محوطه</Typography>
        </Stack>
        <Stack direction="row" spacing={1} alignItems="center">
          <Chip icon={online ? <CloudDone /> : <CloudOff />} label={online ? 'آنلاین' : 'آفلاین'}
            color={online ? 'success' : 'warning'} variant="outlined" />
          <Chip label={`صف: ${pendingCount}`} color={pendingCount ? 'info' : 'default'} variant="outlined" />
          {errorCount > 0 && <Chip label={`خطا: ${errorCount}`} color="error" variant="outlined" />}
          <Button size="small" variant="outlined" startIcon={<Refresh />} onClick={async () => {
            await syncNow(); await refreshQueue()
          }} disabled={syncing || !online}>
            {syncing ? 'در حال همگام‌سازی...' : 'همگام‌سازی'}
          </Button>
        </Stack>
      </Stack>

      {lastMsg && <Alert severity="info">{lastMsg}</Alert>}
      {msg && <Alert severity="success">{msg}</Alert>}
      {err && <Alert severity="error">{err}</Alert>}
      {!online && (
        <Alert severity="warning">
          حالت آفلاین — تخلف و عکس در IndexedDB ذخیره می‌شوند و بعد از وصل‌شدن خودکار ارسال می‌گردند.
        </Alert>
      )}

      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 2 }}>
        <Card>
          <CardContent>
            <Typography fontWeight={800} mb={1.5}>ثبت سریع تخلف (با عکس)</Typography>
            <form onSubmit={submit}>
              <TextField fullWidth label="پلاک خودرو" value={plate}
                onChange={(e) => setPlate(e.target.value)} sx={{ mb: 1.5 }} required />
              {plate.trim() ? (
                <Stack alignItems="center" mb={1.5}>
                  <PlateBox plate={plate} />
                </Stack>
              ) : null}
              <TextField fullWidth select label="نوع تخلف" value={vtype}
                onChange={(e) => setVtype(e.target.value)} sx={{ mb: 1.5 }} required>
                {effectiveTypes.map((t) => (
                  <MenuItem key={t.code} value={t.code}>
                    {t.title} ({money(t.default_penalty_amount)})
                  </MenuItem>
                ))}
              </TextField>
              <Button variant="outlined" component="label" startIcon={<PhotoCamera />} fullWidth sx={{ mb: 1.5 }}>
                {photoName ? `عکس انتخاب شد: ${photoName}` : 'گرفتن / انتخاب عکس'}
                <input type="file" accept="image/*" capture="environment" hidden
                  onChange={(e) => onPhotoPick(e.target.files?.[0] ?? null)} />
              </Button>
              {photo ? (
                <Box component="img" src={photo} alt="preview"
                  sx={{ maxWidth: '100%', maxHeight: 180, borderRadius: 2, mb: 1.5, border: '2px solid #E3EAF2' }} />
              ) : null}
              <TextField fullWidth label="توضیحات (اختیاری)" value={desc}
                onChange={(e) => setDesc(e.target.value)} sx={{ mb: 2 }} multiline rows={2} />
              <Button fullWidth type="submit" variant="contained" size="large" sx={{ py: 1.3 }}>
                ثبت تخلف {online ? '' : '(در صف آفلاین)'}
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardContent>
            <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
              <Typography fontWeight={800}>صف همگام‌سازی (IndexedDB)</Typography>
              <Chip size="small" label={`${queue.length} رکورد`} />
            </Stack>
            {queue.length === 0 ? (
              <Typography color="text.secondary" py={2}>صف خالی است — همه ارسال شده‌اند.</Typography>
            ) : null}
            {queue.map((q) => (
              <Stack key={q.client_ref} direction="row" justifyContent="space-between" alignItems="center"
                sx={{ py: 1, borderBottom: '1px solid #EEE' }}>
                <Stack direction="row" spacing={1.5} alignItems="center">
                  {q.photo_data ? (
                    <Box component="img" src={q.photo_data} alt=""
                      sx={{ width: 48, height: 48, objectFit: 'cover', borderRadius: 1.5, border: '1px solid #CFD8DC' }} />
                  ) : null}
                  <Stack>
                    <Stack direction="row" spacing={1} alignItems="center">
                      <Typography fontWeight={700}>{q.plate}</Typography>
                      <Chip size="small" color={q.status === 'pending' ? 'info' : 'error'}
                        label={q.status === 'pending' ? 'در انتظار ارسال' : 'خطا'} />
                    </Stack>
                    <Typography variant="caption" color="text.secondary">
                      {q.type_code} — {faDate(q.created_at)} — تلاش: {q.tries}
                      {q.last_error ? ` — ${q.last_error}` : ''}
                    </Typography>
                  </Stack>
                </Stack>
                <Button size="small" color="error" startIcon={<DeleteForever />}
                  onClick={() => deleteItem(q.client_ref)}>حذف</Button>
              </Stack>
            ))}
          </CardContent>
        </Card>
      </Box>

      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 2 }}>
        <Card>
          <CardContent>
            <Typography fontWeight={800} mb={1.5}>جستجوی پلاک</Typography>
            <Stack direction="row" spacing={1}>
              <TextField size="small" fullWidth label="پلاک" value={searchPlate}
                onChange={(e) => setSearchPlate(e.target.value)} />
              <Button variant="outlined" startIcon={<Search />} onClick={doSearch} disabled={!online}>جستجو</Button>
            </Stack>
            {searchResult && searchResult.found && searchResult.data ? (
              <Stack spacing={1} mt={2} alignItems="flex-start">
                <PlateBox plate={String(searchResult.data.plate_raw ?? searchResult.data.plate_normalized)} />
                <Typography variant="body2">
                  {String(searchResult.data.brand ?? '—')} {String(searchResult.data.model ?? '')} — {String(searchResult.data.color ?? '—')}
                </Typography>
                <Chip size="small" color={searchResult.data.is_active ? 'success' : 'default'}
                  label={searchResult.data.is_active ? 'فعال' : 'غیرفعال'} />
              </Stack>
            ) : null}
            {searchResult && searchResult.found === false ? (
              <Alert severity="info" sx={{ mt: 2 }}>خودرویی با این پلاک یافت نشد.</Alert>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardContent>
            <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
              <Typography fontWeight={800}>خودروهای حاضر</Typography>
              <Chip size="small" label={online ? 'زنده' : 'آفلاین'} color={online ? 'success' : 'warning'} />
            </Stack>
            {(present ?? []).length === 0 ? (
              <Typography color="text.secondary" py={1}>خودروی حاضر نیست.</Typography>
            ) : null}
            {(present ?? []).slice(0, 8).map((p) => (
              <Stack key={p.id} direction="row" justifyContent="space-between"
                sx={{ py: 1, borderBottom: '1px solid #EEE' }}>
                <Typography fontWeight={700}>{p.plate_normalized}</Typography>
                <Typography variant="caption" color="text.secondary">
                  از {faDate(p.entry_at)} — {Math.round(p.duration_seconds / 60)} دقیقه
                </Typography>
              </Stack>
            ))}
          </CardContent>
        </Card>
      </Box>
    </Stack>
  )
}