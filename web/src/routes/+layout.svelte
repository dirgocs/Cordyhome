<script lang="ts">
	import { to } from '$lib/nav';
	import '../app.css';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { Bell, CalendarClock, House, Settings2, WifiOff, Zap } from '@lucide/svelte';
	import ConfirmOff from '$lib/components/ConfirmOff.svelte';
	import Logo from '$lib/components/Logo.svelte';
	import Toasts from '$lib/components/Toasts.svelte';
	import { home, loadSession, session } from '$lib/state.svelte';
	import { applyTheme, getTheme } from '$lib/theme';
	import { PROTOTYPE } from '$lib/nav';

	let { children } = $props();

	const nav = [
		{ href: '/', label: 'Início', icon: House },
		{ href: '/energia', label: 'Energia', icon: Zap },
		{ href: '/rotinas', label: 'Rotinas', icon: CalendarClock },
		{ href: '/alertas', label: 'Alertas', icon: Bell },
		{ href: '/ajustes', label: 'Ajustes', icon: Settings2 }
	];

	const publicRoute = $derived(page.url.pathname.startsWith('/entrar'));
	const authed = $derived(session.user !== null);

	function isActive(href: string) {
		const path = page.url.pathname;
		if (href === '/') return path === '/' || path.startsWith('/dispositivos');
		return path.startsWith(href);
	}

	$effect(() => {
		// Só aplica se o usuário escolheu um tema; senão respeita o sistema (ou quem hospeda a página).
		const saved = getTheme();
		if (saved !== 'system') applyTheme(saved);
		loadSession().catch(() => {
			session.ready = true;
		});
	});

	// Guarda de rota: sem sessão, vai para /entrar; com sessão, conecta o tempo real.
	$effect(() => {
		if (!session.ready) return;
		if (!authed && !publicRoute) {
			goto(to('/entrar'), { replaceState: true });
		} else if (authed) {
			if (publicRoute) goto(to('/'), { replaceState: true });
			if (!home.loaded) home.refresh().catch(() => {});
			home.connect();
		}
	});
</script>

{#if !session.ready}
	<div class="boot" aria-busy="true"><Logo size={32} /></div>
{:else if publicRoute}
	{@render children()}
{:else if authed}
	<div class="shell">
		<aside class="sidebar">
			<a class="brand" href={to('/')}><Logo /> <span>Cordyhome</span></a>
			<nav aria-label="Principal">
				{#each nav as item (item.href)}
					<a href={to(item.href)} class:active={isActive(item.href)} aria-current={isActive(item.href) ? 'page' : undefined}>
						<item.icon size={19} strokeWidth={1.8} />
						<span>{item.label}</span>
						{#if item.href === '/alertas' && home.unreadAlerts > 0}
							<span class="badge num" aria-label="{home.unreadAlerts} não lidos">{home.unreadAlerts}</span>
						{/if}
					</a>
				{/each}
			</nav>
			<div class="sidebar-foot faint">{session.user?.username}</div>
		</aside>

		<main>
			{#if PROTOTYPE}
				<div class="proto-banner" role="note">Protótipo com dados de demonstração. Nada aqui controla aparelhos reais.</div>
			{/if}
			{#if !home.connected}
				<div class="offline-banner" role="status">
					<WifiOff size={15} /> Reconectando ao hub…
				</div>
			{/if}
			<div class="content">{@render children()}</div>
		</main>

		<nav class="tabbar" aria-label="Principal">
			{#each nav as item (item.href)}
				<a href={to(item.href)} class:active={isActive(item.href)} aria-current={isActive(item.href) ? 'page' : undefined}>
					<span class="tab-icon">
						<item.icon size={22} strokeWidth={isActive(item.href) ? 2.1 : 1.7} />
						{#if item.href === '/alertas' && home.unreadAlerts > 0}
							<span class="dot" aria-label="{home.unreadAlerts} não lidos"></span>
						{/if}
					</span>
					<span>{item.label}</span>
				</a>
			{/each}
		</nav>
	</div>
	<ConfirmOff />
{/if}
<Toasts />

<style>
	.boot {
		display: grid;
		place-items: center;
		height: 100dvh;
		color: var(--text);
		animation: fade 0.6s ease-in-out infinite alternate;
	}
	@keyframes fade {
		from {
			opacity: 0.4;
		}
	}

	.shell {
		min-height: 100dvh;
	}
	main {
		min-width: 0;
	}
	.content {
		max-width: 1080px;
		margin: 0 auto;
		padding: calc(20px + env(safe-area-inset-top)) 16px calc(var(--tabbar) + 32px + env(safe-area-inset-bottom));
	}

	/* ---------- Barra lateral (desktop) ---------- */
	.sidebar {
		display: none;
	}
	@media (min-width: 900px) {
		.shell {
			display: grid;
			grid-template-columns: var(--sidebar) 1fr;
		}
		.sidebar {
			position: sticky;
			top: 0;
			height: 100dvh;
			display: flex;
			flex-direction: column;
			gap: 24px;
			padding: 22px 14px;
			border-right: 1px solid var(--border);
		}
		.content {
			padding: 40px 40px 64px;
		}
		.tabbar {
			display: none !important;
		}
	}
	.brand {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 0 10px;
		font-weight: 650;
		font-size: 16.5px;
		letter-spacing: -0.02em;
		text-decoration: none;
	}
	.sidebar nav {
		display: grid;
		gap: 2px;
	}
	.sidebar nav a {
		display: flex;
		align-items: center;
		gap: 12px;
		height: 40px;
		padding: 0 10px;
		border-radius: 10px;
		color: var(--text-2);
		font-weight: 520;
		text-decoration: none;
	}
	.sidebar nav a:hover {
		background: var(--surface-2);
		color: var(--text);
	}
	.sidebar nav a.active {
		background: var(--surface);
		color: var(--text);
		box-shadow: 0 0 0 1px var(--border);
	}
	.badge {
		margin-left: auto;
		min-width: 22px;
		height: 20px;
		padding: 0 6px;
		border-radius: 999px;
		display: grid;
		place-items: center;
		background: var(--critical);
		color: #fff;
		font-size: 11.5px;
		font-weight: 650;
	}
	.sidebar-foot {
		margin-top: auto;
		padding: 0 10px;
		font-size: 13px;
	}

	/* ---------- Barra inferior (celular) ---------- */
	.tabbar {
		position: fixed;
		z-index: 20;
		left: 0;
		right: 0;
		bottom: 0;
		display: grid;
		grid-template-columns: repeat(5, 1fr);
		height: calc(var(--tabbar) + env(safe-area-inset-bottom));
		padding-bottom: env(safe-area-inset-bottom);
		background: color-mix(in srgb, var(--bg) 88%, transparent);
		backdrop-filter: saturate(1.6) blur(16px);
		-webkit-backdrop-filter: saturate(1.6) blur(16px);
		border-top: 1px solid var(--border);
	}
	.tabbar a {
		display: grid;
		place-items: center;
		align-content: center;
		gap: 3px;
		color: var(--text-3);
		font-size: 11px;
		font-weight: 550;
		text-decoration: none;
	}
	.tabbar a.active {
		color: var(--text);
	}
	.tab-icon {
		position: relative;
		display: grid;
	}
	.dot {
		position: absolute;
		top: -1px;
		right: -3px;
		width: 9px;
		height: 9px;
		border-radius: 50%;
		background: var(--critical);
		border: 2px solid var(--bg);
	}

	.proto-banner {
		padding: 8px 16px;
		background: var(--surface-2);
		color: var(--text-2);
		font-size: 12.5px;
		font-weight: 520;
		text-align: center;
		border-bottom: 1px solid var(--border);
	}
	.offline-banner {
		position: sticky;
		top: 0;
		z-index: 30;
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 8px;
		padding: 8px;
		background: var(--warning-soft);
		color: var(--warning);
		font-size: 13.5px;
		font-weight: 550;
	}
</style>
