import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [sveltekit()],
  server: {
    allowedHosts: ['www.secbleau.com', 'secbleau.com'],
    watch: {
      usePolling: true,
      interval: 500,
    },
    proxy: {
      '/api': {
        target: 'http://api:8000',
        changeOrigin: true,
      },
    },
  },
});
