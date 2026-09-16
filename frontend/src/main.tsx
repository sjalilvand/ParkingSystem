 import '@fontsource/vazirmatn/arabic-400.css'
import '@fontsource/vazirmatn/arabic-700.css'
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './app/App'
import { Providers } from './app/providers'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Providers>
      <App />
    </Providers>
  </React.StrictMode>,
)

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {})
  })
}