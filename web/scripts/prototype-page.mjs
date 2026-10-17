// Gera build-prototype/cordyhome.html: a página do protótipo publicada como artefato.
// O artefato envolve a página no próprio <html>/<head>, então extraímos só o conteúdo e
// trocamos os caminhos absolutos (/app/...) por relativos.
import { readFileSync, writeFileSync } from 'node:fs';

const dir = new URL('../build-prototype/', import.meta.url);
const html = readFileSync(new URL('index.html', dir), 'utf8');

const head = html.slice(html.indexOf('<head>') + 6, html.indexOf('</head>'));
const body = html.slice(html.indexOf('<body') , html.indexOf('</body>')).replace(/^<body[^>]*>/, '');

const keep = head
	.split('\n')
	.map((line) => line.trim())
	.filter((line) => line.startsWith('<link href="/app/') || line.startsWith('<meta name="theme-color"'))
	.join('\n');

const page = `<title>Cordyhome</title>
${keep}
${body.trim()}
`.replaceAll('"/app/', '"./app/');

writeFileSync(new URL('cordyhome.html', dir), page);
console.log('build-prototype/cordyhome.html');
