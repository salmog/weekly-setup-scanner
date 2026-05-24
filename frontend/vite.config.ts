import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',      // Expose to Docker's external network
    port: 3000,           // Force Vite to match the docker-compose mapping
    strictPort: true,     // Crash if port 3000 is taken, rather than silently switching to 3001
    watch: {
      usePolling: true    // Ensures hot-reloads work properly inside Linux containers
    }
  }
});
