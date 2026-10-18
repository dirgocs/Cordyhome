<script lang="ts">
	import { to } from '$lib/nav';
	import { ArrowRight, Bell, Plug, Plus, Power, PowerOff } from '@lucide/svelte';
	import { api } from '$lib/api';
	import AreaChart from '$lib/components/AreaChart.svelte';
	import DeviceTile from '$lib/components/DeviceTile.svelte';
	import { kwh, money, watts, wattsParts } from '$lib/format';
	import { errorMessage, home, toast } from '$lib/state.svelte';
	import type { Device, HomeData } from '$lib/types';

	type Filter = 'all' | 'on' | 'issues';

	let summary = $state<HomeData | null>(null);
	let filter = $state<Filter>('all');
	let roomBusy = $state<number | null>(null);

	async function load() {
		try {
			summary = await api.get<HomeData>('/home');
		} catch (e) {
			toast(errorMessage(e), 'error');
		}
	}

	$effect(() => {
		// Recarrega quando o hub grava energia (1×/min) e a cada 30 s para a curva de potência.
		void home.versions.energy;
		load();
		const timer = setInterval(load, 30_000);
		return () => clearInterval(timer);
	});

	const devices = $derived(home.devices.filter((d) => d.enabled));
	const livePower = $derived(devices.reduce((s, d) => s + (d.online ? (d.power_w ?? 0) : 0), 0));
	const onCount = $derived(devices.filter((d) => d.online && d.is_on).length);
	const offline = $derived(devices.filter((d) => !d.online));
	const [powerNum, powerUnit] = $derived(wattsParts(livePower));

	function matches(d: Device) {
		if (filter === 'on') return d.online && d.is_on;
		if (filter === 'issues') return !d.online || !!d.last_error;
		return true;
	}

	const groups = $derived.by(() => {
		const visible = devices.filter(matches);
		const sections = home.rooms
			.map((room) => ({ room, devices: visible.filter((d) => d.room_id === room.id) }))
			.filter((g) => g.devices.length > 0);
		const loose = visible.filter((d) => !home.rooms.some((r) => r.id === d.room_id));
		if (loose.length) sections.push({ room: { id: 0, name: 'Sem cômodo', sort_order: 999 }, devices: loose });
		return sections;
	});

	async function roomPower(roomId: number, on: boolean, roomDevices: Device[]) {
		roomBusy = roomId;
		try {
			const res = await api.post<{ changed: number; failed: number[] }>(`/rooms/${roomId}/power`, { on });
			const protectedCount = on ? 0 : roomDevices.filter((d) => d.confirm_off && d.is_on).length;
			let message = `${res.changed} ${res.changed === 1 ? 'aparelho' : 'aparelhos'} ${on ? 'ligado' : 'desligado'}${res.changed === 1 ? '' : 's'}`;
			if (protectedCount) message += ` · ${protectedCount} protegido${protectedCount > 1 ? 's' : ''} mantido${protectedCount > 1 ? 's' : ''}`;
			if (res.failed.length) message += ` · ${res.failed.length} falharam`;
			toast(message, res.failed.length ? 'error' : 'default');
		} catch (e) {
			toast(errorMessage(e), 'error');
		} finally {
			roomBusy = null;
		}
	}

	const todayRaw = new Date().toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long' });
	const today = todayRaw.charAt(0).toUpperCase() + todayRaw.slice(1);
	const powerHistory = $derived(
		(summary?.power_history ?? []).map((p) => ({ ts: p.ts, value: p.w }))
	);
</script>

<svelte:head><title>Início · Cordyhome</title></svelte:head>

{#if home.loaded && devices.length === 0}
	<section class="onboarding card">
		<span class="onboarding-icon"><Plug size={26} strokeWidth={1.6} /></span>
		<h1>Vamos conectar sua casa</h1>
		<p class="muted">
			Traga seus aparelhos inteligentes para o Cordyhome. Leva uns 2 minutos, e depois disso
			eles funcionam pela sua rede local, sem nuvem e sem assinatura.
		</p>
		<a class="btn primary" href={to('/adicionar')}>Adicionar aparelhos <ArrowRight size={17} /></a>
	</section>
{:else}
	<p class="date eyebrow">{today}</p>

	<section class="hero card" aria-label="Consumo agora">
		<div class="hero-main">
			<span class="eyebrow">Consumo agora</span>
			<p class="power" aria-live="polite">
				<span class="power-num">{powerNum}</span><span class="power-unit">{powerUnit}</span>
			</p>
			<p class="muted hero-sub">
				{onCount} de {devices.length} ligados
				{#if offline.length}
					· <a href="#issues" onclick={() => (filter = 'issues')} class="warn-link">{offline.length} sem conexão</a>
				{/if}
			</p>
		</div>
		<div class="hero-chart">
			<AreaChart points={powerHistory} format={watts} compact height={84} ariaLabel="Consumo total nas últimas 3 horas" />
			<span class="faint chart-caption">Últimas 3 horas</span>
		</div>
	</section>

	<section class="stats">
		<a class="stat card" href={to('/energia?range=today')}>
			<span class="eyebrow">Hoje</span>
			<strong>{summary ? money(summary.today.cost) : '—'}</strong>
			<span class="muted num">{summary ? kwh(summary.today.kwh) : ' '}</span>
		</a>
		<a class="stat card" href={to('/energia?range=month')}>
			<span class="eyebrow">Este mês</span>
			<strong>{summary ? money(summary.month.cost) : '—'}</strong>
			<span class="muted">
				{#if summary?.month.projected_cost != null}
					Previsão {money(summary.month.projected_cost)}
				{:else}
					{summary ? kwh(summary.month.kwh) : ' '}
				{/if}
			</span>
		</a>
	</section>

	{#if home.unreadAlerts > 0}
		<a class="alert-strip" href={to('/alertas')}>
			<Bell size={17} />
			<span>{home.unreadAlerts} {home.unreadAlerts === 1 ? 'alerta não lido' : 'alertas não lidos'}</span>
			<ArrowRight size={16} class="push" />
		</a>
	{/if}

	<div class="toolbar" id="issues">
		<div class="toolbar-title">
			<h2>Aparelhos</h2>
			<a class="btn sm ghost" href={to('/adicionar')}><Plus size={16} /> Adicionar</a>
		</div>
		<div class="filters" role="radiogroup" aria-label="Filtrar aparelhos">
			{#each [['all', 'Todos'], ['on', 'Ligados'], ['issues', 'Com problema']] as [value, label] (value)}
				<button type="button" role="radio" aria-checked={filter === value} onclick={() => (filter = value as Filter)}>
					{label}
				</button>
			{/each}
		</div>
	</div>

	{#if !home.loaded}
		<div class="grid">
			{#each Array(6) as _, i (i)}<div class="skeleton" style="height: 124px"></div>{/each}
		</div>
	{:else if groups.length === 0}
		<p class="empty muted">
			{filter === 'on' ? 'Nenhum aparelho ligado agora.' : 'Tudo funcionando. Nenhum aparelho com problema.'}
		</p>
	{/if}

	{#each groups as group (group.room.id)}
		{@const roomPowerW = group.devices.reduce((s, d) => s + (d.online ? (d.power_w ?? 0) : 0), 0)}
		{@const anyOn = group.devices.some((d) => d.online && d.is_on)}
		<section class="room">
			<header>
				<h3>{group.room.name}</h3>
				<span class="faint num">{watts(roomPowerW)}</span>
				{#if group.room.id !== 0 && group.devices.length > 1}
					<button
						class="btn ghost sm room-action"
						type="button"
						disabled={roomBusy === group.room.id}
						onclick={() => roomPower(group.room.id, !anyOn, group.devices)}
					>
						{#if anyOn}<PowerOff size={15} /> Desligar tudo{:else}<Power size={15} /> Ligar tudo{/if}
					</button>
				{/if}
			</header>
			<div class="grid">
				{#each group.devices as device (device.id)}
					<DeviceTile {device} />
				{/each}
			</div>
		</section>
	{/each}
{/if}

<style>
	.date {
		margin-bottom: 10px;
	}
	.hero {
		display: grid;
		gap: 12px;
		padding: 20px 20px 16px;
		overflow: hidden;
	}
	.power {
		display: flex;
		align-items: baseline;
		gap: 6px;
		margin: 4px 0 2px;
		line-height: 1;
	}
	.power-num {
		font-size: 56px;
		font-weight: 600;
		letter-spacing: -0.035em;
	}
	.power-unit {
		font-size: 22px;
		font-weight: 550;
		color: var(--text-2);
	}
	.hero-sub {
		font-size: 14px;
	}
	.warn-link {
		color: var(--warning);
		font-weight: 550;
		text-underline-offset: 3px;
	}
	.hero-chart {
		display: grid;
		gap: 4px;
		min-width: 0;
	}
	.chart-caption {
		font-size: 12px;
		text-align: right;
	}
	@media (min-width: 720px) {
		.hero {
			grid-template-columns: minmax(220px, 0.8fr) 1.2fr;
			align-items: end;
			padding: 24px 24px 18px;
		}
		.power-num {
			font-size: 64px;
		}
	}

	.stats {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 12px;
		margin-top: 12px;
	}
	.stat {
		display: grid;
		gap: 2px;
		padding: 16px 18px;
		text-decoration: none;
		transition: border-color 0.15s;
	}
	.stat:hover {
		border-color: var(--border-strong);
	}
	.stat strong {
		font-size: 24px;
		font-weight: 600;
		letter-spacing: -0.02em;
		margin-top: 4px;
	}
	.stat span:last-child {
		font-size: 13.5px;
	}

	.alert-strip {
		display: flex;
		align-items: center;
		gap: 10px;
		margin-top: 12px;
		padding: 12px 16px;
		border-radius: var(--radius);
		background: var(--warning-soft);
		color: var(--warning);
		font-weight: 550;
		text-decoration: none;
	}
	.alert-strip :global(.push) {
		margin-left: auto;
	}

	.toolbar-title {
		display: flex;
		align-items: center;
		gap: 8px;
	}
	.toolbar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		flex-wrap: wrap;
		margin: 32px 0 8px;
	}
	.filters {
		display: flex;
		gap: 6px;
	}
	.filters button {
		height: 30px;
		padding: 0 12px;
		border-radius: 999px;
		border: 1px solid var(--border);
		background: transparent;
		color: var(--text-2);
		font-size: 13px;
		font-weight: 550;
	}
	.filters button[aria-checked='true'] {
		background: var(--text);
		border-color: var(--text);
		color: var(--bg);
	}

	.room {
		margin-top: 20px;
	}
	.room header {
		display: flex;
		align-items: baseline;
		gap: 8px;
		margin-bottom: 10px;
		min-height: 32px;
	}
	.room-action {
		margin-left: auto;
		align-self: center;
		color: var(--text-2);
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 10px;
	}
	@media (min-width: 560px) {
		.grid {
			grid-template-columns: repeat(auto-fill, minmax(168px, 1fr));
			gap: 12px;
		}
	}
	.empty {
		padding: 24px 0;
	}

	.onboarding {
		max-width: 560px;
		margin: 8vh auto 0;
		padding: 36px 28px;
		display: grid;
		gap: 14px;
		justify-items: start;
	}
	.onboarding-icon {
		display: grid;
		place-items: center;
		width: 52px;
		height: 52px;
		border-radius: 14px;
		background: var(--accent-soft);
		color: var(--accent-strong);
		margin-bottom: 6px;
	}
	.onboarding .btn {
		margin-top: 8px;
		height: 44px;
	}
</style>
