import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import { offlineDB } from './db'

export function useOnlineStatus() {
  const [online, setOnline] = useState(typeof navigator !== 'undefined' ? navigator.onLine : true)
  useEffect(() => {
    const up = () => setOnline(true)
    const down = () => setOnline(false)
    window.addEventListener('online', up)
    window.removeEventListener('online', up)
    window.removeEventListener('offline', down)
    window.addEventListener('offline', down)
    return () => {
      window.removeEventListener('online', up)
      window.removeEventListener('offline', down)
    }
  }, [])
  return online
}

export interface SyncResult { sent: number; failed: number }

async function dataUrlToBlob(dataUrl: string): Promise<Blob> {
  const r = await fetch(dataUrl)
  return r.blob()
}

async function uploadPhoto(dataUrl: string, photoRef: string): Promise<string | null> {
  try {
    const blob = await dataUrlToBlob(dataUrl)
    const fd = new FormData()
    fd.append('file', blob, 'photo.jpg')
    fd.append('client_ref', photoRef)
    fd.append('prefix', 'violations')
    const r = await api.post('/files', fd)
    return r.data.id as string
  } catch {
    return null
  }
}

export async function syncPendingViolations(): Promise<SyncResult> {
  const items = await offlineDB.pending_violations.where('status').equals('pending').toArray()
  let sent = 0
  let failed = 0
  for (const item of items) {
    try {
      let imageFileId: string | null = null
      if (item.photo_data) {
        imageFileId = await uploadPhoto(item.photo_data, `${item.client_ref}:photo`)
        if (!imageFileId) {
          await offlineDB.pending_violations.update(item.client_ref, { tries: item.tries + 1, last_error: 'photo upload failed' })
          failed++
          continue
        }
      }
      await api.post('/violations', {
        plate_raw: item.plate,
        violation_type_code: item.type_code,
        description: item.description ?? null,
        client_ref: item.client_ref,
        image_file_id: imageFileId,
      })
      await offlineDB.pending_violations.delete(item.client_ref)
      sent++
    } catch (err) {
      const e = err as { response?: { status?: number; data?: { error?: { message?: string } } } }
      if (e.response) {
        await offlineDB.pending_violations.update(item.client_ref, {
          status: 'error',
          tries: item.tries + 1,
          last_error: e.response.data?.error?.message ?? `HTTP ${e.response.status}`,
        })
        failed++
      } else {
        await offlineDB.pending_violations.update(item.client_ref, { tries: item.tries + 1 })
        failed++
      }
    }
  }
  return { sent, failed }
}

export function useOfflineSync(pollMs = 30000) {
  const online = useOnlineStatus()
  const [syncing, setSyncing] = useState(false)
  const [lastMsg, setLastMsg] = useState('')

  const syncNow = useCallback(async () => {
    if (!navigator.onLine) return
    setSyncing(true)
    try {
      const r = await syncPendingViolations()
      if (r.sent || r.failed) setLastMsg(`${r.sent} ارسال شد، ${r.failed} ناموفق`)
    } finally {
      setSyncing(false)
    }
  }, [])

  useEffect(() => {
    const t = setTimeout(syncNow, 1500)
    const iv = setInterval(syncNow, pollMs)
    const up = () => setTimeout(syncNow, 1200)
    window.addEventListener('online', up)
    return () => {
      clearTimeout(t)
      clearInterval(iv)
      window.removeEventListener('online', up)
    }
  }, [pollMs, syncNow])

  return { online, syncing, lastMsg, syncNow }
}