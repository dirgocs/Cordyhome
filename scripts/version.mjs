// Versão única do Cordyhome. O arquivo VERSION na raiz é a fonte; este script a copia para
// o hub, a interface e o app de desktop.
//
//   node scripts/version.mjs          confere se todos os arquivos estão na mesma versão
//   node scripts/version.mjs 0.3.0    muda a versão em todos (e atualiza o uv.lock)
//
// Publicar uma versão = mudar a versão, descrever no CHANGELOG.md e fazer o merge na main.
// O workflow "Release" cria a release vX.Y.Z com o instalador quando essa tag ainda não existe.
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const read = (p) => readFileSync(join(root, p), 'utf8');
const write = (p, s) => writeFileSync(join(root, p), s);

const json = (path) => ({
	path,
	get: () => JSON.parse(read(path)).version,
	set: (v) => {
		const data = JSON.parse(read(path));
		data.version = v;
		if (data.packages?.['']) data.packages[''].version = v; // package-lock.json
		write(path, JSON.stringify(data, null, '\t') + '\n');
	}
});

const regex = (path, re) => ({
	path,
	get: () => read(path).match(re)?.[2],
	set: (v) => write(path, read(path).replace(re, `$1${v}$3`))
});

const targets = [
	regex('VERSION', /^()([^\s]+)(\s*)$/),
	regex('hub/pyproject.toml', /(^version = ")([^"]+)(")/m),
	regex('hub/cordyhome/__init__.py', /(__version__ = ")([^"]+)(")/),
	json('web/package.json'),
	json('web/package-lock.json'),
	json('desktop/package.json'),
	json('desktop/package-lock.json'),
	regex('desktop/src-tauri/Cargo.toml', /(\[package\][^[]*?\nversion = ")([^"]+)(")/)
];

const wanted = process.argv[2];
if (wanted) {
	if (!/^\d+\.\d+\.\d+$/.test(wanted)) {
		console.error('Use o formato X.Y.Z, por exemplo 0.3.0');
		process.exit(1);
	}
	for (const t of targets) t.set(wanted);
	execFileSync('uv', ['lock'], { cwd: join(root, 'hub'), stdio: 'inherit' });
	console.log(`Versão ${wanted} aplicada. Descreva as mudanças no CHANGELOG.md.`);
} else {
	const version = targets[0].get();
	const wrong = targets.filter((t) => t.get() !== version);
	for (const t of wrong) console.error(`${t.path}: ${t.get()} (esperado ${version})`);
	if (!read('CHANGELOG.md').includes(`## ${version}`)) {
		console.error(`CHANGELOG.md não tem a seção "## ${version}"`);
		wrong.push('CHANGELOG.md');
	}
	if (wrong.length) process.exit(1);
	console.log(version);
}
