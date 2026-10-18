// Copia o hub e a interface compilada para dentro do pacote do app de desktop.
// O uv (desktop/src-tauri/resources/bin) é baixado à parte pelo workflow de release.
import { cpSync, existsSync, mkdirSync, rmSync } from 'node:fs';
import { dirname, join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const target = join(root, 'desktop', 'src-tauri', 'resources');
const skip = new Set(['tests', '.venv', '__pycache__', '.pytest_cache', '.ruff_cache']);

const webBuild = join(root, 'web', 'build');
if (!existsSync(join(webBuild, 'index.html'))) {
	console.error('Interface não compilada. Rode antes: cd web && npm ci && npm run build');
	process.exit(1);
}

for (const dir of ['hub', 'web']) rmSync(join(target, dir), { recursive: true, force: true });
mkdirSync(join(target, 'bin'), { recursive: true });

cpSync(join(root, 'hub'), join(target, 'hub'), {
	recursive: true,
	filter: (src) => !relative(join(root, 'hub'), src).split(sep).some((part) => skip.has(part))
});
cpSync(webBuild, join(target, 'web'), { recursive: true });

const uv = join(target, 'bin', process.platform === 'win32' ? 'uv.exe' : 'uv');
if (!existsSync(uv)) console.warn(`Atenção: ${relative(root, uv)} não existe; o app não vai conseguir preparar o Python.`);
console.log(`Recursos prontos em ${relative(root, target)}`);
