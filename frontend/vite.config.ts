import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
  build: { sourcemap: true, rolldownOptions: { output: { codeSplitting: { groups: [
    { name: 'charts', test: /node_modules[\\/]recharts|node_modules[\\/]d3-/ },
    { name: 'topology', test: /node_modules[\\/]@xyflow/ },
    { name: 'react', test: /node_modules[\\/]react(?:-dom)?[\\/]/ },
  ] } } } },
});
