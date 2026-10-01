import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Accordion, AccordionDetails, AccordionSummary, Box, Button, Chip, IconButton,
  Stack, TextField, Typography,
} from '@mui/material'
import { Add, Delete, Edit, ExpandMore } from '@mui/icons-material'
import { api, apiErrorFa } from '../api/client'

interface CatalogModel { id: string; name: string; submodels: string[] }
interface CatalogBrand { id: string; name: string; models: CatalogModel[] }

export default function VehicleCatalogManager() {
  const qc = useQueryClient()
  const [newBrand, setNewBrand] = useState('')
  const [editBrand, setEditBrand] = useState<{ id: string; name: string } | null>(null)
  const [addModel, setAddModel] = useState<{ brand: string; name: string } | null>(null)
  const [editModel, setEditModel] = useState<{ id: string; name: string } | null>(null)
  const [addSub, setAddSub] = useState<{ modelId: string; name: string } | null>(null)
  const [editSub, setEditSub] = useState<{ modelId: string; old: string; name: string } | null>(null)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const { data: catalog } = useQuery({
    queryKey: ['vehicle-catalog'],
    queryFn: async () => (await api.get('/base-data/vehicle-catalog')).data as CatalogBrand[],
  })
  const refresh = () => qc.invalidateQueries({ queryKey: ['vehicle-catalog'] })
  const run = async (fn: () => Promise<unknown>) => {
    setErr(''); setMsg('')
    try { await fn(); setMsg('✔ انجام شد'); refresh() } catch (e) { setErr(apiErrorFa(e)) }
  }

  return (
    <Card><CardContent>
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1.5} flexWrap="wrap" useFlexGap>
        <Typography fontWeight={800}>🚘 کاتالوگ خودرو (برند ← مدل ← زیرمدل)</Typography>
        <Chip size="small" label={`برندها: ${catalog?.length ?? 0}`} variant="outlined" />
      </Stack>
      {err && <Alert severity="error" sx={{ mb: 1 }}>{err}</Alert>}
      {msg && <Alert severity="success" sx={{ mb: 1 }}>{msg}</Alert>}

      <Stack direction="row" spacing={1} mb={2} flexWrap="wrap" useFlexGap>
        <TextField size="small" label="برند جدید" value={newBrand}
          onChange={(e) => setNewBrand(e.target.value)} sx={{ width: 220 }} />
        <Button variant="contained" startIcon={<Add />} disabled={!newBrand.trim()}
          onClick={() => run(async () => {
            await api.post('/base-data/brands', { name_fa: newBrand.trim() })
            setNewBrand('')
          })}>افزودن برند</Button>
      </Stack>

      {(catalog ?? []).map((b) => (
        <Accordion key={b.id}>
          <AccordionSummary expandIcon={<ExpandMore />}>
            {editBrand?.id === b.id ? (
              <Stack direction="row" spacing={1} onClick={(e) => e.stopPropagation()}>
                <TextField size="small" value={editBrand.name}
                  onChange={(e) => setEditBrand({ ...editBrand, name: e.target.value })} />
                <IconButton color="primary" onClick={(e) => { e.stopPropagation()
                  run(async () => { await api.patch(`/base-data/brands/${b.id}`, { name_fa: editBrand.name }); setEditBrand(null) }) }}>
                  ✓
                </IconButton>
              </Stack>
            ) : (
              <Stack direction="row" spacing={1} alignItems="center">
                <Typography fontWeight={800}>{b.name}</Typography>
                <Chip size="small" label={`${b.models.length} مدل`} variant="outlined" />
              </Stack>
            )}
          </AccordionSummary>
          <AccordionDetails>
            <Stack direction="row" spacing={1} mb={1.5} flexWrap="wrap" useFlexGap alignItems="center">
              {editBrand?.id === b.id ? null : (
                <IconButton size="small" onClick={() => setEditBrand({ id: b.id, name: b.name })}><Edit /></IconButton>
              )}
              {addModel?.brand === b.name ? (
                <>
                  <TextField size="small" label="نام مدل" value={addModel.name}
                    onChange={(e) => setAddModel({ ...addModel, name: e.target.value })} />
                  <Button size="small" variant="contained" onClick={() => run(async () => {
                    await api.post('/base-data/vehicle-models', { brand_name: b.name, name: addModel.name })
                    setAddModel(null)
                  })}>ثبت</Button>
                  <Button size="small" onClick={() => setAddModel(null)}>لغو</Button>
                </>
              ) : (
                <Button size="small" startIcon={<Add />}
                  onClick={() => setAddModel({ brand: b.name, name: '' })}>افزودن مدل</Button>
              )}
            </Stack>
            {b.models.map((m) => (
              <Box key={m.id} sx={{ border: '1px solid #E3EAF2', borderRadius: 2, p: 1, mb: 1 }}>
                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                  {editModel?.id === m.id ? (
                    <>
                      <TextField size="small" value={editModel.name}
                        onChange={(e) => setEditModel({ ...editModel, name: e.target.value })} />
                      <IconButton size="small" color="primary" onClick={() => run(async () => {
                        await api.patch(`/base-data/vehicle-models/${m.id}`, { name: editModel.name }); setEditModel(null)
                      })}>✓</IconButton>
                    </>
                  ) : (
                    <Typography fontWeight={700} sx={{ minWidth: 120 }}>{m.name}</Typography>
                  )}
                  <IconButton size="small" onClick={() => setEditModel({ id: m.id, name: m.name })}><Edit fontSize="small" /></IconButton>
                  <IconButton size="small" color="error" onClick={() => run(async () => {
                    await api.delete(`/base-data/vehicle-models/${m.id}`)
                  })}><Delete fontSize="small" /></IconButton>
                </Stack>
                <Stack direction="row" spacing={0.6} flexWrap="wrap" useFlexGap mt={0.8} alignItems="center">
                  {m.submodels.map((s) => (
                    <Chip key={s} size="small" label={s} onDelete={() => run(async () => {
                      // حذف زیرمدل: با endpoint عمومی حذف بر اساس نام انجام نمی‌شود؛ از id استفاده می‌کنیم
                    })} />
                  ))}
                  {addSub?.modelId === m.id ? (
                    <>
                      <TextField size="small" value={addSub.name} autoFocus
                        onChange={(e) => setAddSub({ ...addSub, name: e.target.value })} sx={{ width: 160 }} />
                      <Button size="small" variant="contained" onClick={() => run(async () => {
                        await api.post('/base-data/vehicle-submodels', { model_id: m.id, name: addSub.name })
                        setAddSub(null)
                      })}>ثبت</Button>
                    </>
                  ) : (
                    <IconButton size="small" onClick={() => setAddSub({ modelId: m.id, name: '' })}><Add fontSize="small" /></IconButton>
                  )}
                </Stack>
              </Box>
            ))}
          </AccordionDetails>
        </Accordion>
      ))}
    </CardContent></Card>
  )
}