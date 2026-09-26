<script lang="ts">
	import { to } from '$lib/nav';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { Table2, ChartColumn } from '@lucide/svelte';
	import { api } from '$lib/api';
	import BarList from '$lib/components/BarList.svelte';
	import ColumnChart from '$lib/components/ColumnChart.svelte';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Segmented from '$lib/components/Segmented.svelte';
	import { bucketLabels, kwh, kwhTick, money, number } from '$lib/format';
	import { errorMessage, home, toast } from '$lib/state.svelte';
	import type { EnergyReport, RangeKey } from '$lib/types';

	const ranges: { value: RangeKey; label: string }[] = [
		{ value: 'today', label: 'Hoje' },
		{ value: 'yesterday', label: 'Ontem' },
		{ value: '7d', label: '7 dias' },
		{ value: '30d', label: '30 dias' },
		{ value: 'month', label: 'Este mês' },
		{ value: '12m', label: '12 meses' }
	];
	const periodText: Record<RangeKey, string> = {
		today: 'hoje',
		yesterday: 'ontem',
		'7d': 'nos últimos 7 dias',
		'30d': 'nos últimos 30 dias',
		month: 'neste mês',
		'12m': 'nos últimos 12 meses'
	};

	const range = $derived((page.url.searchParams.get('range') as RangeKey) ?? 'today');
	const roomId = $derived(page.url.searchParams.get('room') ?? '');

	let report = $state<EnergyReport | null>(null);
	let showTable = $state(false);

	function setParam(key: string, value: string) {
		const params = new URLSearchParams(page.url.searchParams);
		if (value) params.set(key, value);
		else params.delete(key);
		const query = params.toString();
		goto(to(`/energia${query ? `?${query}` : ''}`), { replaceState: true, keepFocus: true, noScroll: true });
	}

	$effect(() => {
		void home.versions.energy;
		const query = `range=${range}${roomId ? `&room_id=${roomId}` : ''}`;
		// Mantém o gráfico anterior enquanto carrega (sem piscar skeleton).
		api
			.get<EnergyReport>(`/energy?${query}`)
			.then((r) => (report = r))
			.catch((e) => toast(errorMessage(e), 'error'));
	});

	const columns = $derived(
		(report?.series ?? []).map((p) => {
			const [label, tooltip] = bucketLabels(p.start, report!.bucket);
			return { label, tooltip, value: p.kwh };
		})
	);
	const currentIndex = $derived.by(() => {
		if (!report) return -1;
		const now = Date.now();
		const starts = report.series.map((p) => new Date(p.start).getTime());
		const end = new Date(report.end).getTime();
		return starts.findIndex((start, i) => start <= now && now < (starts[i + 1] ?? end));
	});
	const peak = $derived(
		columns.length ? columns.reduce((a, b) => (b.value > a.value ? b : a), columns[0]) : null
	);
	const deviceItems = $derived(
		(report?.devices ?? [])
			.filter((d) => d.kwh > 0.0005)
			.map((d) => ({
				key: d.device_id,
				label: d.name,
				sublabel: home.roomName(d.room_id),
				value: d.kwh,
				display: money(d.cost),
				secondary: kwh(d.kwh),
				href: to(`/dispositivos/${d.device_id}`)
			}))
	);
	const roomItems = $derived(
		(report?.rooms ?? [])
			.filter((r) => r.kwh > 0.0005)
			.map((r) => ({
				key: r.room_id ?? 0,
				label: home.roomName(r.room_id),
				value: r.kwh,
				display: money(r.cost),
				secondary: kwh(r.kwh)
			}))
	);
</script>

<svelte:head><title>Energia · Cordyhome</title></svelte:head>

<PageHeader title="Energia" subtitle="Consumo e custo estimado pela sua tarifa." />

<div class="filters">
	<Segmented label="Período" options={ranges} value={range} onchange={(v) => setParam('range', v === 'today' ? '' : v)} />
	<select class="input room" aria-label="Cômodo" value={roomId} onchange={(e) => setParam('room', e.currentTarget.value)}>
		<option value="">Casa toda</option>
		{#each home.rooms as room (room.id)}<option value={String(room.id)}>{room.name}</option>{/each}
	</select>
</div>

<section class="card summary">
	<div class="figures">
		<div>
			<span class="eyebrow">Custo {periodText[range]}</span>
			<p class="hero">{report ? money(report.cost) : '—'}</p>
			<p class="muted num">
				{report ? kwh(report.total_kwh) : ' '}
				{#if report}· {money(report.tariff_per_kwh)}/kWh{/if}
			</p>
		</div>
		{#if report?.projected_cost != null}
			<div class="projection">
				<span class="eyebrow">Previsão para o mês</span>
				<p class="projection-value">{money(report.projected_cost)}</p>
				<p class="muted num">{kwh(report.projected_kwh)}</p>
			</div>
		{/if}
	</div>

	<div class="chart-head">
		<h2>Consumo {report?.bucket === 'hour' ? 'por hora' : report?.bucket === 'day' ? 'por dia' : 'por mês'}</h2>
		<button class="btn ghost sm" type="button" onclick={() => (showTable = !showTable)} aria-pressed={showTable}>
			{#if showTable}<ChartColumn size={15} /> Gráfico{:else}<Table2 size={15} /> Tabela{/if}
		</button>
	</div>

	{#if showTable}
		<div class="table-wrap">
			<table>
				<thead><tr><th>Período</th><th>kWh</th><th>Custo</th></tr></thead>
				<tbody>
					{#each columns as c, i (i)}
						<tr>
							<td>{c.tooltip}</td>
							<td class="num">{number(c.value, 2)}</td>
							<td class="num">{money(c.value * (report?.tariff_per_kwh ?? 0))}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{:else if report}
		<ColumnChart
			{columns}
			current={currentIndex}
			format={kwh}
			tickFormat={kwhTick}
			height={230}
			ariaLabel="Consumo em kWh {periodText[range]}"
		/>
		{#if peak && peak.value > 0}
			<p class="faint caption">Pico: {peak.tooltip}, {kwh(peak.value)}. Barra mais clara = período em andamento.</p>
		{/if}
	{:else}
		<div class="skeleton" style="height: 230px"></div>
	{/if}
</section>

<div class="breakdown">
	<section class="card panel">
		<h2>Por aparelho</h2>
		<BarList items={deviceItems} />
	</section>
	{#if !roomId}
		<section class="card panel">
			<h2>Por cômodo</h2>
			<BarList items={roomItems} />
		</section>
	{/if}
</div>

<style>
	.filters {
		display: flex;
		flex-wrap: wrap;
		gap: 10px;
		align-items: center;
		margin-bottom: 16px;
	}
	.room {
		width: auto;
		min-width: 160px;
		height: 38px;
	}
	.summary {
		padding: 20px;
	}
	.figures {
		display: flex;
		flex-wrap: wrap;
		gap: 16px 48px;
		align-items: flex-end;
		margin-bottom: 24px;
	}
	.hero {
		font-size: 48px;
		font-weight: 600;
		letter-spacing: -0.035em;
		line-height: 1.05;
		margin: 6px 0 4px;
	}
	.projection-value {
		font-size: 24px;
		font-weight: 600;
		letter-spacing: -0.02em;
		margin: 4px 0 2px;
	}
	.chart-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 12px;
	}
	.chart-head h2 {
		font-size: 15px;
	}
	.caption {
		font-size: 12.5px;
		margin-top: 10px;
	}
	.table-wrap {
		max-height: 360px;
		overflow: auto;
	}
	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 14px;
	}
	th {
		text-align: left;
		font-weight: 550;
		color: var(--text-2);
		position: sticky;
		top: 0;
		background: var(--surface);
	}
	th,
	td {
		padding: 8px 4px;
		border-bottom: 1px solid var(--border);
	}
	td.num,
	th:not(:first-child) {
		text-align: right;
	}
	.breakdown {
		display: grid;
		gap: 12px;
		margin-top: 12px;
	}
	@media (min-width: 900px) {
		.breakdown {
			grid-template-columns: 1fr 1fr;
			align-items: start;
		}
		.summary {
			padding: 24px;
		}
	}
	.panel {
		padding: 18px 20px 8px;
	}
	.panel h2 {
		font-size: 15px;
		margin-bottom: 4px;
	}
</style>
