import React, { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Accordion, AccordionDetails, AccordionSummary, Alert, Box, Button, Card,
  CardContent, Chip, IconButton, Stack, TextField, Typography,
} from '@mui/material'
import { Add, Delete, Edit, ExpandMore } from '@mui/icons-material'
import { api, apiErrorFa } from '../api/client'

interface SubModel { id: string; name: string }
interface CatalogModel { id: string; name: string; submodels?: SubModel[] }
interface CatalogBrand { id?: string; name: string; models?: CatalogModel[] }

class CatalogBoundary extends React.Component<{ children: React.ReactNode }, { err: string | null }> {
  state = { err: null as string | null }
  static getDerivedStateFromError(e: unknown) { return { err: String(e) } }
  render() {
    if (this.state.err) {
      return <Alert severity="error">خطا در کاتالوگ: {this.state.err}</Alert>
    }
    return this.props.children
  }
}

function ManagerInner() {
  const qc = useQueryClient()
  const [newBrand, setNewBrand] = useState('')
  const [editBrand, setEditBrand] = useState<{ id: string; name: string } | null>(null)
  const [addModel, setAddModel] = useState<{ brandId: string; name: string } | null>(null)
  const [editModel, setEditModel] = useState<{ id: string; name: string } | null>(null)
  const [addSub, setAddSub] = useState<{ modelId: string; name: string } | null>(null)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const { data: catalog } = useQuery({
    queryKey: ['vehicle-catalog'],
    queryFn: async () => (await api.get('/base-data/vehicle-catalog')).data as CatalogBrand[],
  })
  const brands: CatalogBrand[] = Array.isArray(catalog) ? catalog : []
  const refresh = () => qc.invalidateQueries({ queryKey: ['vehicle-catalog'] })
  const run = async (fn: () => Promise<unknown>) => {
    setErr(''); setMsg('')
    try { await fn(); setMsg('انجام شد'); refresh() } catch (e) { setErr(apiErrorFa(e)) }
  }

  return (
    <Card><CardContent>
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1.5} flexWrap="wrap" useFlexGap>
        <Typography fontWeight={800}>کاتالوگ خودرو (برند، مدل، زیرمدل)</Typography>
        <Chip size="small" label={`برندها: ${brands.length}`} variant="outlined" />
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

      {brands.map((b) => {
        const models: CatalogModel[] = b.models ?? []
        return (
          <Accordion key={b.id ?? b.name}>
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
                  <Chip size="small" label={`${models.length} مدل`} variant="outlined" />
                </Stack>
              )}
            </AccordionSummary>
            <AccordionDetails>
              <Stack direction="row" spacing={1} mb={1.5} flexWrap="wrap" useFlexGap alignItems="center">
                {editBrand?.id === b.id ? null : (
                  <IconButton size="small" onClick={() => setEditBrand({ id: b.id ?? '', name: b.name })}><Edit /></IconButton>
                )}
                {addModel?.brandId === b.id ? (
                  <>
                    <TextField size="small" label="نام مدل" value={addModel.name} autoFocus
                      onChange={(e) => setAddModel({ ...addModel, name: e.target.value })} />
                    <Button size="small" variant="contained" onClick={() => run(async () => {
                      await api.post('/base-data/vehicle-models', { brand_name: b.name, name: addModel.name })
                      setAddModel(null)
                    })}>ثبت</Button>
                    <Button size="small" onClick={() => setAddModel(null)}>لغو</Button>
                  </>
                ) : (
                  <Button size="small" startIcon={<Add />}
                    onClick={() => setAddModel({ brandId: b.id ?? '', name: '' })}>افزودن مدل</Button>
                )}
              </Stack>
              {models.map((m) => {
                const subs: SubModel[] = m.submodels ?? []
                return (
                  <Box key={m.id ?? m.name} sx={{ border: '1px solid #E3EAF2', borderRadius: 2, p: 1, mb: 1 }}>
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
                        <Typography fontWeight={700} sx={{ minWidth: 110 }}>{m.name}</Typography>
                      )}
                      <IconButton size="small" onClick={() => setEditModel({ id: m.id ?? '', name: m.name })}><Edit fontSize="small" /></IconButton>
                      <IconButton size="small" color="error" onClick={() => run(async () => {
                        await api.delete(`/base-data/vehicle-models/${m.id}`)
                      })}><Delete fontSize="small" /></IconButton>
                    </Stack>
                    <Stack direction="row" spacing={0.6} flexWrap="wrap" useFlexGap mt={0.8} alignItems="center">
                      {subs.map((s) => (
                        <Chip key={s.id ?? s.name} size="small" label={s.name} onDelete={() => run(async () => {
                          await api.delete(`/base-data/vehicle-submodels/${s.id}`)
                        })} />
                      ))}
                      {addSub?.modelId === m.id ? (
                        <>
                          <TextField size="small" value={addSub.name} autoFocus
                            onChange={(e) => setAddSub({ ...addSub, name: e.target.value })} sx={{ width: 150 }} />
                          <Button size="small" variant="contained" onClick={() => run(async () => {
                            await api.post('/base-data/vehicle-submodels', { model_id: m.id, name: addSub.name })
                            setAddSub(null)
                          })}>ثبت</Button>
                          <Button size="small" onClick={() => setAddSub(null)}>لغو</Button>
                        </>
                      ) : (
                        <IconButton size="small" onClick={() => setAddSub({ modelId: m.id ?? '', name: '' })}><Add fontSize="small" /></IconButton>
                      )}
                    </Stack>
                  </Box>
                )
              })}
            </AccordionDetails>
          </Accordion>
        )
      })}
    </CardContent></Card>
  )
}

export default function VehicleCatalogManager() {
  return (
    <CatalogBoundary>
      <ManagerInner />
    </CatalogBoundary>
  )
}