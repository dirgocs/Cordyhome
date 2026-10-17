<script lang="ts">
	import { CalendarClock, Plus } from '@lucide/svelte';
	import { api } from '$lib/api';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import ScheduleForm from '$lib/components/ScheduleForm.svelte';
	import ScheduleRow from '$lib/components/ScheduleRow.svelte';
	import { errorMessage, home, toast } from '$lib/state.svelte';
	import type { Schedule } from '$lib/types';

	let schedules = $state<Schedule[] | null>(null);
	let open = $state(false);
	let editing = $state<Schedule | null>(null);

	async function load() {
		try {
			schedules = await api.get<Schedule[]>('/schedules');
		} catch (e) {
			toast(errorMessage(e), 'error');
		}
	}

	$effect(() => {
		void home.versions.schedules;
		load();
	});

	const active = $derived((schedules ?? []).filter((s) => s.enabled));
	const paused = $derived((schedules ?? []).filter((s) => !s.enabled));

	function create() {
		editing = null;
		open = true;
	}
</script>

<svelte:head><title>Rotinas · Cordyhome</title></svelte:head>

<PageHeader title="Rotinas" subtitle="Ligue e desligue aparelhos automaticamente.">
	{#snippet actions()}
		{#if home.devices.length}
			<button class="btn primary" type="button" onclick={create}><Plus size={17} /> Nova rotina</button>
		{/if}
	{/snippet}
</PageHeader>

{#if schedules === null}
	<div class="skeleton" style="height: 200px"></div>
{:else if schedules.length === 0}
	<section class="card empty">
		<CalendarClock size={28} strokeWidth={1.6} />
		<h2>Nenhuma rotina ainda</h2>
		<p class="muted">
			Exemplos: ligar a cafeteira às 6h50 nos dias úteis, ou desligar o ar-condicionado às 6h.
			Rotinas rodam no hub, mesmo com o celular desligado.
		</p>
		{#if home.devices.length}
			<button class="btn primary" type="button" onclick={create}><Plus size={17} /> Criar rotina</button>
		{/if}
	</section>
{:else}
	<section class="card group">
		<h2 class="eyebrow">Ativas · por próxima execução</h2>
		{#if active.length}
			<ul>
				{#each active as s (s.id)}
					<ScheduleRow schedule={s} onedit={(x) => { editing = x; open = true; }} onchange={load} />
				{/each}
			</ul>
		{:else}
			<p class="faint none">Todas as rotinas estão pausadas.</p>
		{/if}
	</section>
	{#if paused.length}
		<section class="card group">
			<h2 class="eyebrow">Pausadas</h2>
			<ul>
				{#each paused as s (s.id)}
					<ScheduleRow schedule={s} onedit={(x) => { editing = x; open = true; }} onchange={load} />
				{/each}
			</ul>
		</section>
	{/if}
{/if}

<ScheduleForm {open} schedule={editing} onclose={() => (open = false)} onsaved={load} />

<style>
	.group {
		padding: 16px 20px 4px;
		margin-bottom: 12px;
	}
	.group h2 {
		margin-bottom: 2px;
	}
	ul {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.none {
		padding: 12px 0 16px;
		font-size: 14px;
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
	.empty p {
		max-width: 520px;
	}
	.empty .btn {
		margin-top: 6px;
	}
	@media (max-width: 560px) {
		:global(.page-header) {
			align-items: flex-start;
		}
	}
</style>
