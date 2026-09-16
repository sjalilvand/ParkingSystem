import Dexie, { type Table } from 'dexie'

export interface PendingViolation {
  client_ref: string
  plate: string
  type_code: string
  description?: string
  photo_data?: string
  created_at: string
  tries: number
  status: 'pending' | 'error'
  last_error?: string
}

export interface KV {
  key: string
  value: unknown
}

class ParkingOfflineDB extends Dexie {
  pending_violations!: Table<PendingViolation, string>
  kv!: Table<KV, string>

  constructor() {
    super('parking-offline')
    this.version(1).stores({
      pending_violations: 'client_ref, status, created_at',
      kv: 'key',
    })
  }
}

export const offlineDB = new ParkingOfflineDB()