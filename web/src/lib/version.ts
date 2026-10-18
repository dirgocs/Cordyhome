export const APP_VERSION = __APP_VERSION__;

const RELEASES = 'https://api.github.com/repos/dirgocs/Cordyhome/releases/latest';
export const RELEASES_PAGE = 'https://github.com/dirgocs/Cordyhome/releases/latest';

/** Compara versões X.Y.Z: positivo quando `a` é mais nova que `b`. */
export function compareVersions(a: string, b: string): number {
	const pa = a.replace(/^v/, '').split('.').map(Number);
	const pb = b.replace(/^v/, '').split('.').map(Number);
	for (let i = 0; i < 3; i++) {
		const diff = (pa[i] || 0) - (pb[i] || 0);
		if (diff) return diff;
	}
	return 0;
}

/** Versão publicada mais recente no GitHub, ou null se não der para consultar (sem internet). */
export async function latestRelease(): Promise<string | null> {
	try {
		const res = await fetch(RELEASES, { headers: { accept: 'application/vnd.github+json' } });
		if (!res.ok) return null;
		const data = (await res.json()) as { tag_name?: string };
		return data.tag_name?.replace(/^v/, '') ?? null;
	} catch {
		return null;
	}
}
