import { Navigate, Route, Routes } from 'react-router-dom'
import MainLayout from '../layouts/MainLayout'
import Login from '../pages/Login'
import Dashboard from '../pages/Dashboard'
import GatePanel from '../pages/GatePanel'
import Structure from '../pages/Structure'
import FieldOps from '../pages/FieldOps'
import Users from '../pages/Users'
import BaseData from '../pages/BaseData'
import Vehicles from '../pages/Vehicles'
import Permits from '../pages/Permits'
import Parking from '../pages/Parking'
import AccessEvents from '../pages/AccessEvents'
import Debts from '../pages/Debts'
import Violations from '../pages/Violations'
import Tariffs from '../pages/Tariffs'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<MainLayout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/gate" element={<GatePanel />} />
        <Route path="/structure" element={<Structure />} />
        <Route path="/field" element={<FieldOps />} />
        <Route path="/base-data" element={<BaseData />} />
        <Route path="/users" element={<Users />} />
        <Route path="/vehicles" element={<Vehicles />} />
        <Route path="/permits" element={<Permits />} />
        <Route path="/parking" element={<Parking />} />
        <Route path="/access-events" element={<AccessEvents />} />
        <Route path="/debts" element={<Debts />} />
        <Route path="/violations" element={<Violations />} />
        <Route path="/tariffs" element={<Tariffs />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}