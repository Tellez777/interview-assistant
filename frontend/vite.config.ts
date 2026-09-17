import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Escucha en todas las interfaces (no solo localhost) para poder
    // entrar desde el teléfono u otro dispositivo en la misma red local.
    host: true,
    proxy: {
      // `ws: true` es necesario para /api/live/stream (WebSocket de Live
      // Mode) — sin esto Vite solo reenvía HTTP, no upgrades de WebSocket.
      // El proxy corre en esta misma máquina, así que sigue apuntando a
      // 127.0.0.1:8000 aunque el navegador que se conecta sea el del
      // teléfono — el que habla con el backend siempre es este servidor.
      '/api': { target: 'http://127.0.0.1:8000', ws: true },
    },
  },
})
