export type Theme = 'system' | 'light' | 'dark';

const KEY = 'cordyhome.theme';

export function getTheme(): Theme {
	try {
		const value = localStorage.getItem(KEY);
		return value === 'light' || value === 'dark' ? value : 'system';
	} catch {
		return 'system';
	}
}

export function applyTheme(theme: Theme) {
	const root = document.documentElement;
	if (theme === 'system') root.removeAttribute('data-theme');
	else root.setAttribute('data-theme', theme);
	try {
		if (theme === 'system') localStorage.removeItem(KEY);
		else localStorage.setItem(KEY, theme);
	} catch {
		/* armazenamento indisponível (modo privado): o tema vale só nesta sessão */
	}
}
