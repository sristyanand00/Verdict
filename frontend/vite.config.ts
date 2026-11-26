import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // the FastAPI backend runs on port 8000 (plan section 18)
    proxy: { '/api': 'http://localhost:8000' },
  },
})
