import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

const hub = process.env.CORDYHOME_HUB ?? 'http://127.0.0.1:8420';
// Build de protótipo (artefato): rotas por hash e hub simulado no navegador.
const prototype = process.env.VITE_PROTOTYPE === '1';

export default defineConfig({
	plugins: [
		sveltekit({
			compilerOptions: {
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},
			// SPA estática servida pelo próprio hub.
			adapter: adapter({ fallback: 'index.html', pages: prototype ? 'build-prototype' : 'build' }),
			router: { type: prototype ? 'hash' : 'pathname' },
			// O artefato reserva nomes começados por "_".
			appDir: prototype ? 'app' : '_app'
		})
	],
	server: {
		proxy: {
			'/api': { target: hub, ws: true, changeOrigin: false }
		}
	}
});
