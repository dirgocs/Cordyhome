<script lang="ts">
	import { niceTicks } from '$lib/chart';
	import { timeOf } from '$lib/format';

	export interface Point {
		ts: number; // segundos
		value: number;
	}
	interface Props {
		points: Point[];
		format: (value: number) => string;
		tickFormat?: (value: number) => string;
		height?: number;
		/** Sem eixos: só a forma, para cabeçalhos. A leitura por toque continua. */
		compact?: boolean;
		ariaLabel: string;
	}
	let {
		points,
		format,
		tickFormat = format,
		height = 200,
		compact = false,
		ariaLabel
	}: Props = $props();

	let width = $state(0);
	let active = $state<number | null>(null);

	const axisW = $derived(compact ? 0 : 44);
	const bottom = $derived(compact ? 2 : 24);
	const top = 6;
	const plotW = $derived(Math.max(0, width - axisW));
	const plotH = $derived(height - bottom - top);
	const ticks = $derived(niceTicks(Math.max(...points.map((p) => p.value), 0), compact ? 2 : 4));
	const maxTick = $derived(ticks[ticks.length - 1] || 1);
	const t0 = $derived(points[0]?.ts ?? 0);
	const t1 = $derived(points[points.length - 1]?.ts ?? 1);

	const x = (ts: number) => axisW + (t1 === t0 ? plotW : ((ts - t0) / (t1 - t0)) * plotW);
	const y = (v: number) => top + plotH - (v / maxTick) * plotH;

	const line = $derived(
		points.map((p, i) => `${i ? 'L' : 'M'}${x(p.ts).toFixed(1)},${y(p.value).toFixed(1)}`).join('')
	);
	const area = $derived(
		points.length
			? `${line}L${x(t1).toFixed(1)},${top + plotH}L${x(t0).toFixed(1)},${top + plotH}Z`
			: ''
	);
	const timeTicks = $derived.by(() => {
		if (compact || points.length < 2) return [];
		const count = Math.max(2, Math.min(6, Math.floor(plotW / 80)));
		return Array.from({ length: count }, (_, i) => t0 + ((t1 - t0) * i) / (count - 1));
	});

	function nearest(clientX: number, rect: DOMRect) {
		if (!points.length) return;
		const px = clientX - rect.left;
		let best = 0;
		let bestDist = Infinity;
		for (let i = 0; i < points.length; i++) {
			const d = Math.abs(x(points[i].ts) - px);
			if (d < bestDist) {
				bestDist = d;
				best = i;
			}
		}
		active = best;
	}

	function onKey(event: KeyboardEvent) {
		if (!points.length) return;
		const step = Math.max(1, Math.round(points.length / 24));
		if (event.key === 'ArrowRight') active = Math.min(points.length - 1, (active ?? -1) + step);
		else if (event.key === 'ArrowLeft') active = Math.max(0, (active ?? points.length) - step);
		else return;
		event.preventDefault();
	}

	const tip = $derived(active != null ? points[active] : null);
</script>

<div class="chart" bind:clientWidth={width} style:height="{height}px">
	{#if width > 0 && points.length > 1}
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
			onpointermove={(e) => nearest(e.clientX, e.currentTarget.getBoundingClientRect())}
			onpointerdown={(e) => nearest(e.clientX, e.currentTarget.getBoundingClientRect())}
			onpointerleave={() => (active = null)}
		>
			{#if !compact}
				{#each ticks as t (t)}
					<line class="grid" x1={axisW} x2={width} y1={y(t)} y2={y(t)} />
					<text class="tick" x={axisW - 8} y={y(t)} dy="0.32em" text-anchor="end">
						{tickFormat(t)}
					</text>
				{/each}
				{#each timeTicks as ts, i (i)}
					<text
						class="tick"
						x={x(ts)}
						y={height - 6}
						text-anchor={i === 0 ? 'start' : i === timeTicks.length - 1 ? 'end' : 'middle'}
					>
						{timeOf(ts * 1000)}
					</text>
				{/each}
			{/if}
			<path class="area" d={area} />
			<path class="line" d={line} />
			{#if tip}
				<line class="cross" x1={x(tip.ts)} x2={x(tip.ts)} y1={top} y2={top + plotH} />
				<circle class="dot" cx={x(tip.ts)} cy={y(tip.value)} r="4.5" />
			{:else}
				<circle
					class="dot"
					cx={x(points[points.length - 1].ts)}
					cy={y(points[points.length - 1].value)}
					r="4"
				/>
			{/if}
		</svg>
		{#if tip}
			<div
				class="tooltip"
				style:left="{Math.min(Math.max(x(tip.ts), 60), width - 60)}px"
				style:top="{Math.max(0, y(tip.value) - 10)}px"
			>
				<strong>{format(tip.value)}</strong>
				<span>{timeOf(tip.ts * 1000)}</span>
			</div>
		{/if}
	{:else if width > 0}
		<div class="empty">Coletando dados…</div>
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
		shape-rendering: crispEdges;
	}
	.tick {
		fill: var(--text-3);
		font-size: 11.5px;
		font-variant-numeric: tabular-nums;
	}
	.area {
		fill: var(--accent-mark);
		opacity: 0.12;
	}
	.line {
		fill: none;
		stroke: var(--accent-mark);
		stroke-width: 2;
		stroke-linejoin: round;
		stroke-linecap: round;
	}
	.cross {
		stroke: var(--text-3);
		stroke-width: 1;
	}
	.dot {
		fill: var(--accent-mark);
		stroke: var(--surface);
		stroke-width: 2;
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
	.empty {
		display: grid;
		place-items: center;
		height: 100%;
		color: var(--text-3);
		font-size: 13.5px;
	}
</style>
