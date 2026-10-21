<script lang="ts">
	import { to } from '$lib/nav';
	import { ChevronLeft, ChevronRight, CircleCheck } from '@lucide/svelte';
	import { api } from '$lib/api';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import { INTEGRATIONS } from '$lib/integrations';
	import type { TuyaStatus } from '$lib/types';

	let status = $state<Record<string, TuyaStatus>>({});

	$effect(() => {
		for (const integration of INTEGRATIONS) {
			api
				.get<TuyaStatus>(integration.statusPath)
				.then((s) => (status = { ...status, [integration.id]: s }))
				.catch(() => {});
		}
	});
</script>

<svelte:head><title>Adicionar aparelhos · Cordyhome</title></svelte:head>

<a class="back" href={to('/')}><ChevronLeft size={18} /> Início</a>

<PageHeader title="Adicionar aparelhos" subtitle="Escolha de onde vêm os aparelhos. Depois de conectados, eles funcionam pela sua rede local." />

<ul class="integrations">
	{#each INTEGRATIONS as integration (integration.id)}
		{@const s = status[integration.id]}
		<li>
			<a class="card integration" href={to(integration.href)}>
				<span class="text">
					<span class="name">{integration.name}</span>
					<span class="muted">{integration.brands}</span>
					<span class="faint kinds">{integration.kinds}</span>
					{#if s?.linked}
						<span class="linked"><CircleCheck size={14} /> {integration.linkedLabel} · {s.imported_devices} {s.imported_devices === 1 ? 'aparelho' : 'aparelhos'}</span>
					{/if}
				</span>
				<ChevronRight size={20} class="chevron" />
			</a>
		</li>
	{/each}
</ul>

<p class="faint more">Outras marcas e protocolos entram nesta lista conforme as integrações forem lançadas.</p>

<style>
	.back {
		display: inline-flex;
		align-items: center;
		gap: 2px;
		margin: 0 0 16px -4px;
		color: var(--text-2);
		font-weight: 550;
		font-size: 14px;
		text-decoration: none;
	}
	.integrations {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: 12px;
		max-width: 720px;
	}
	.integration {
		display: flex;
		align-items: center;
		gap: 16px;
		padding: 18px 20px;
		color: inherit;
		text-decoration: none;
	}
	.integration:hover {
		border-color: var(--border-strong, var(--border));
	}
	.text {
		display: grid;
		gap: 4px;
		flex: 1;
		font-size: 14px;
	}
	.name {
		font-size: 16px;
		font-weight: 650;
	}
	.kinds {
		font-size: 13px;
	}
	.linked {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		margin-top: 4px;
		color: var(--accent);
		font-size: 13px;
		font-weight: 550;
	}
	.more {
		margin-top: 16px;
		font-size: 13px;
		max-width: 720px;
	}
</style>
