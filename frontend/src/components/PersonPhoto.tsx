import { useEffect, useState } from 'react'
import { Avatar, Box, IconButton } from '@mui/material'
import { PhotoCamera } from '@mui/icons-material'
import { api } from '../api/client'

interface Props {
  personId: string
  photoFileId?: string | null
  onUploaded?: () => void
  size?: number
}

export default function PersonPhoto({ personId, photoFileId, onUploaded, size = 48 }: Props) {
  const [url, setUrl] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!photoFileId) { setUrl(null); return }
    let dead = false
    api.get(`/files/${photoFileId}/url`)
      .then((r) => { if (!dead) setUrl(r.data.url) })
      .catch(() => { if (!dead) setUrl(null) })
    return () => { dead = true }
  }, [photoFileId])

  const upload = async (file: File | null) => {
    if (!file) return
    setBusy(true)
    try {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('prefix', 'persons')
      const up = await api.post('/files', fd)
      await api.patch(`/persons/${personId}`, { photo_file_id: up.data.id })
      onUploaded?.()
    } finally {
      setBusy(false)
    }
  }

  return (
    <Box sx={{ position: 'relative', display: 'inline-flex' }}>
      <Avatar src={url ?? undefined} sx={{ width: size, height: size, bgcolor: '#E3EAF2', color: '#90A4AE' }} />
      <IconButton size="small" component="label"
        sx={{ position: 'absolute', bottom: -6, left: -6, bgcolor: '#fff', boxShadow: 1 }}>
        <PhotoCamera fontSize="inherit" />
        <input type="file" accept="image/*" hidden disabled={busy}
          onChange={(e) => upload(e.target.files?.[0] ?? null)} />
      </IconButton>
    </Box>
  )
}