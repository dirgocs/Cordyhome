<script lang="ts">
	import { niceTicks } from '$lib/chart';

	export interface Column {
		label: string;
		tooltip: string;
		value: number;
	}
	interface Props {
		columns: Column[];
		format: (value: number) => string;
		tickFormat?: (value: number) => string;
		height?: number;
		/** Índice da coluna do período atual (ainda em andamento). */
		current?: number;
		ariaLabel: string;
	}
	let { columns, format, tickFormat = format, height = 220, current = -1, ariaLabel }: Props =
		$props();

	let width = $state(0);
	let active = $state<number | null>(null);

	const axisW = 44;
	const bottom = 26;
	const top = 8;
	const plotH = $derived(height - bottom - top);
	const plotW = $derived(Math.max(0, width - axisW));
	const ticks = $derived(niceTicks(Math.max(...columns.map((c) => c.value), 0)));
	const maxTick = $derived(ticks[ticks.length - 1] || 1);
	const band = $derived(columns.length ? plotW / columns.length : 0);
	const barW = $derived(Math.max(2, Math.min(24, band - 2)));
	const labelEvery = $derived(Math.max(1, Math.ceil(columns.length / Math.max(1, plotW / 46))));

	const y = (v: number) => top + plotH - (v / maxTick) * plotH;

	function barPath(i: number, value: number): string {
		const x = axisW + i * band + (band - barW) / 2;
		const h = Math.max(value > 0 ? 2 : 0, (value / maxTick) * plotH);
		const r = Math.min(4, barW / 2, h);
		const y0 = top + plotH;
		const y1 = y0 - h;
		// Topo arredondado (4px), base reta no eixo.
		return `M${x},${y0} V${y1 + r} Q${x},${y1} ${x + r},${y1} H${x + barW - r} Q${x + barW},${y1} ${x + barW},${y1 + r} V${y0} Z`;
	}

	function onKey(event: KeyboardEvent) {
		if (!columns.length) return;
		if (event.key === 'ArrowRight') active = Math.min(columns.length - 1, (active ?? -1) + 1);
		else if (event.key === 'ArrowLeft') active = Math.max(0, (active ?? columns.length) - 1);
		else return;
		event.preventDefault();
	}

	const tip = $derived(active != null ? columns[active] : null);
	const tipX = $derived(active != null ? axisW + active * band + band / 2 : 0);
</script>

<div class="chart" bind:clientWidth={width} style:height="{height}px">
	{#if width > 0}
		<!-- Gráfico navegável por teclado (setas); os valores também aparecem em texto/tabela. -->
		<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
		<svg
			{width}
			{height}
			role="img"
			aria-label={ariaLabel}
			tabindex="0"
			onkeydown={onKey}
			onblur={() => (active = null)}
		>
			{#each ticks as t (t)}
				<line class="grid" x1={axisW} x2={width} y1={y(t)} y2={y(t)} />
				<text class="tick" x={axisW - 8} y={y(t)} dy="0.32em" text-anchor="end">
					{tickFormat(t)}
				</text>
			{/each}
			{#each columns as c, i (i)}
				<path
					class="bar"
					class:dim={active != null && active !== i}
					class:current={i === current}
					d={barPath(i, c.value)}
				/>
				{#if i % labelEvery === 0}
					<text class="tick" x={axisW + i * band + band / 2} y={height - 8} text-anchor="middle">
						{c.label}
					</text>
				{/if}
				<!-- Alvo de toque: a faixa inteira, não só a barra. -->
				<rect
					role="presentation"
					class="hit"
					x={axisW + i * band}
					y={top}
					width={band}
					height={plotH}
					onpointerenter={() => (active = i)}
					onpointerleave={() => (active = null)}
					onpointerdown={() => (active = i)}
				/>
			{/each}
		</svg>
		{#if tip}
			<div
				class="tooltip"
				style:left="{Math.min(Math.max(tipX, 70), width - 70)}px"
				style:top="{Math.max(0, y(tip.value) - 8)}px"
			>
				<strong>{format(tip.value)}</strong>
				<span>{tip.tooltip}</span>
			</div>
		{/if}
	{/if}
</div>

<style>
	.chart {
		position: relative;
		width: 100%;
		user-select: none;
		touch-action: pan-y;
	}
	svg {
		display: block;
		overflow: visible;
	}
	svg:focus-visible {
		outline: 2px solid var(--focus);
		outline-offset: 4px;
	}
	.grid {
		stroke: var(--grid);
		stroke-width: 1;
		shape-rendering: crispEdges;
	}
	.tick {
		fill: var(--text-3);
		font-size: 11.5px;
		font-variant-numeric: tabular-nums;
	}
	.bar {
		fill: var(--accent-mark);
		transition: opacity 0.12s;
	}
	.bar.current {
		fill: color-mix(in srgb, var(--accent-mark) 55%, var(--surface));
	}
	.bar.dim {
		opacity: 0.35;
	}
	.hit {
		fill: transparent;
	}
	.tooltip {
		position: absolute;
		transform: translate(-50%, -100%);
		display: grid;
		gap: 1px;
		padding: 7px 10px;
		border-radius: 9px;
		background: var(--text);
		color: var(--bg);
		font-size: 12.5px;
		white-space: nowrap;
		pointer-events: none;
		box-shadow: var(--shadow-lg);
	}
	.tooltip strong {
		font-size: 14px;
		font-weight: 600;
	}
	.tooltip span {
		opacity: 0.75;
	}
</style>
