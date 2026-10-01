import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { MenuItem, Stack, TextField } from '@mui/material'
import { api } from '../api/client'

interface CatalogBrand { name: string; models: { name: string; submodels: string[] }[] }

interface Props {
  brand: string
  model: string
  onChange: (brand: string, model: string) => void
}

export default function CatalogPicker({ brand, model, onChange }: Props) {
  const { data: catalog } = useQuery({
    queryKey: ['vehicle-catalog'],
    queryFn: async () => (await api.get('/base-data/vehicle-catalog')).data as CatalogBrand[],
    staleTime: 24 * 3600 * 1000,
  })
  const brands = catalog ?? []
  const brandObj = useMemo(() => brands.find((b) => b.name === brand), [brands, brand])
  const modelObj = useMemo(
    () => (brandObj?.models ?? []).find((m) => model === m.name || model.startsWith(m.name + ' ')),
    [brandObj, model])

  return (
    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
      <TextField select size="small" label="برند (از کاتالوگ)" value={brandObj ? brand : ''}
        onChange={(e) => {
          const b = e.target.value
          const first = brands.find((x) => x.name === b)?.models[0]?.name ?? ''
          onChange(b, first)
        }}>
        {brands.map((b) => <MenuItem key={b.name} value={b.name}>{b.name}</MenuItem>)}
      </TextField>
      <TextField select size="small" label="مدل" value={modelObj?.name ?? ''} disabled={!brandObj}
        onChange={(e) => onChange(brand, e.target.value)}>
        {(brandObj?.models ?? []).map((m) => <MenuItem key={m.name} value={m.name}>{m.name}</MenuItem>)}
      </TextField>
      <TextField select size="small" label="زیرمدل"
        value={modelObj && model.length > modelObj.name.length ? model.slice(modelObj.name.length).trim() : ''}
        disabled={!modelObj}
        onChange={(e) => {
          const s = e.target.value
          onChange(brand, s ? `${modelObj!.name} ${s}` : modelObj!.name)
        }}>
        <MenuItem value="">—</MenuItem>
        {(modelObj?.submodels ?? []).map((s) => <MenuItem key={s} value={s}>{s}</MenuItem>)}
      </TextField>
    </Stack>
  )
}