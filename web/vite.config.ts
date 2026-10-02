import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const DEV_ORIGINS = new Set(['http://localhost:5173', 'http://127.0.0.1:5173'])

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // changeOrigin rewrites Host to 127.0.0.1:8765 so the server's DNS-rebinding check passes
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8765',
        changeOrigin: true,
        // map only the dev origin to the server's own; anything else passes through and gets the server's 403
        configure: proxy => proxy.on('proxyReq', (req, incoming) => {
          if (DEV_ORIGINS.has(incoming.headers.origin ?? '')) req.setHeader('origin', 'http://127.0.0.1:8765')
        }),
      },
    },
  },
})
