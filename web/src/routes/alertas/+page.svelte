<script lang="ts">
	import { to } from '$lib/nav';
	import { BellOff, CircleCheck, OctagonAlert, TriangleAlert, Info } from '@lucide/svelte';
	import { api } from '$lib/api';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Segmented from '$lib/components/Segmented.svelte';
	import { dateTime, relative, timeOf } from '$lib/format';
	import { errorMessage, home, toast } from '$lib/state.svelte';
	import type { Alert } from '$lib/types';

	let filter = $state<'unread' | 'all'>('unread');
	let items = $state<Alert[] | null>(null);

	async function load() {
		try {
			const res = await api.get<{ unread: number; items: Alert[] }>(`/alerts?filter=${filter}`);
			items = res.items;
			home.unreadAlerts = res.unread;
		} catch (e) {
			toast(errorMessage(e), 'error');
		}
	}

	$effect(() => {
		void filter;
		void home.versions.alerts;
		load();
	});

	async function ack(alert: Alert) {
		try {
			const res = await api.post<{ unread: number }>(`/alerts/${alert.id}/ack`);
			home.unreadAlerts = res.unread;
			load();
		} catch (e) {
			toast(errorMessage(e), 'error');
		}
	}

	async function ackAll() {
		try {
			await api.post('/alerts/ack-all');
			home.unreadAlerts = 0;
			load();
		} catch (e) {
			toast(errorMessage(e), 'error');
		}
	}

	const severity = {
		critical: { icon: OctagonAlert, label: 'Crítico' },
		warning: { icon: TriangleAlert, label: 'Atenção' },
		info: { icon: Info, label: 'Informação' }
	};
	const kindLabel: Record<string, string> = {
		offline: 'Sem conexão',
		high_power: 'Consumo alto',
		command_failed: 'Comando falhou',
		schedule_failed: 'Rotina falhou'
	};
</script>

<svelte:head><title>Alertas · Cordyhome</title></svelte:head>

<PageHeader title="Alertas" subtitle="Falhas de conexão, consumo acima do limite e comandos que não funcionaram.">
	{#snippet actions()}
		{#if home.unreadAlerts > 0}
			<button class="btn" type="button" onclick={ackAll}>Marcar todos como lidos</button>
		{/if}
	{/snippet}
</PageHeader>

<div class="filters">
	<Segmented
		label="Filtro"
		value={filter}
		options={[
			{ value: 'unread', label: `Não lidos${home.unreadAlerts ? ` (${home.unreadAlerts})` : ''}` },
			{ value: 'all', label: 'Todos' }
		]}
		onchange={(v) => (filter = v)}
	/>
</div>

{#if items === null}
	<div class="skeleton" style="height: 160px"></div>
{:else if items.length === 0}
	<section class="card empty">
		{#if filter === 'unread'}<CircleCheck size={28} strokeWidth={1.6} />{:else}<BellOff size={28} strokeWidth={1.6} />{/if}
		<h2>{filter === 'unread' ? 'Tudo em dia' : 'Nenhum alerta registrado'}</h2>
		<p class="muted">O Cordyhome avisa aqui quando uma tomada sai do ar, consome demais ou não obedece a um comando.</p>
	</section>
{:else}
	<ul class="card list">
		{#each items as alert (alert.id)}
			{@const sev = severity[alert.severity] ?? severity.info}
			<li class="item" class:read={alert.acknowledged}>
				<span class="sev {alert.severity}" title={sev.label}><sev.icon size={18} aria-hidden="true" /></span>
				<div class="body">
					<div class="meta">
						<span class="kind">{kindLabel[alert.kind] ?? alert.kind}</span>
						<span class="faint">· {sev.label}</span>
						<time class="faint" datetime={new Date(alert.created_at * 1000).toISOString()} title={dateTime(alert.created_at)}>
							{relative(alert.created_at)}
						</time>
					</div>
					<p>{alert.message}</p>
					<div class="foot">
						{#if alert.resolved_at && alert.kind !== 'command_failed' && alert.kind !== 'schedule_failed'}
							<span class="pill accent">Resolvido às {timeOf(alert.resolved_at * 1000)}</span>
						{:else if !alert.resolved_at}
							<span class="pill warning">Em andamento</span>
						{/if}
						{#if alert.device_id}<a href={to(`/dispositivos/${alert.device_id}`)}>Ver aparelho</a>{/if}
					</div>
				</div>
				{#if !alert.acknowledged}
					<button class="btn sm" type="button" onclick={() => ack(alert)}>Lido</button>
				{/if}
			</li>
		{/each}
	</ul>
{/if}

<style>
	.filters {
		margin-bottom: 16px;
	}
	.list {
		list-style: none;
		margin: 0;
		padding: 4px 20px;
	}
	.item {
		display: flex;
		gap: 14px;
		align-items: flex-start;
		padding: 16px 0;
		border-bottom: 1px solid var(--border);
	}
	.item:last-child {
		border-bottom: 0;
	}
	.sev {
		display: grid;
		place-items: center;
		flex: none;
		width: 34px;
		height: 34px;
		border-radius: 10px;
		background: var(--surface-2);
		color: var(--info);
	}
	.sev.warning {
		background: var(--warning-soft);
		color: var(--warning);
	}
	.sev.critical {
		background: var(--critical-soft);
		color: var(--critical);
	}
	.body {
		flex: 1;
		min-width: 0;
		display: grid;
		gap: 4px;
	}
	.meta {
		display: flex;
		flex-wrap: wrap;
		gap: 4px;
		font-size: 13px;
	}
	.kind {
		font-weight: 600;
	}
	.meta time {
		margin-left: auto;
	}
	.foot {
		display: flex;
		align-items: center;
		gap: 12px;
		margin-top: 4px;
		font-size: 13.5px;
	}
	.foot a {
		color: var(--text-2);
		font-weight: 550;
		text-underline-offset: 3px;
	}
	.read .body p {
		color: var(--text-2);
	}
	.read .sev {
		opacity: 0.6;
	}
	.empty {
		display: grid;
		justify-items: start;
		gap: 10px;
		padding: 28px 24px;
		color: var(--text-2);
	}
	.empty h2 {
		color: var(--text);
	}
</style>
