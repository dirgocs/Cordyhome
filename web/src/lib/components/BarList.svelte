<script lang="ts">
	export interface BarItem {
		key: string | number;
		label: string;
		sublabel?: string;
		value: number;
		display: string;
		secondary?: string;
		href?: string;
	}
	let { items, emptyText = 'Sem consumo no período.' }: { items: BarItem[]; emptyText?: string } =
		$props();
	const max = $derived(Math.max(...items.map((i) => i.value), 0) || 1);
	const total = $derived(items.reduce((sum, i) => sum + i.value, 0) || 1);
</script>

{#if items.length === 0}
	<p class="empty">{emptyText}</p>
{:else}
	<ol class="list">
		{#each items as item (item.key)}
			<li>
				<svelte:element this={item.href ? 'a' : 'div'} href={item.href} class="row">
					<div class="labels">
						<span class="label">{item.label}</span>
						{#if item.sublabel}<span class="sub">{item.sublabel}</span>{/if}
					</div>
					<div class="values">
						<span class="value num">{item.display}</span>
						<span class="sub num">
							{item.secondary ?? ''}{item.secondary ? ' · ' : ''}{Math.round(
								(item.value / total) * 100
							)}%
						</span>
					</div>
					<div class="track" aria-hidden="true">
						<div class="fill" style:width="{(item.value / max) * 100}%"></div>
					</div>
				</svelte:element>
			</li>
		{/each}
	</ol>
{/if}

<style>
	.list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
	}
	.row {
		display: grid;
		grid-template-columns: 1fr auto;
		gap: 4px 12px;
		padding: 11px 0;
		text-decoration: none;
		border-bottom: 1px solid var(--border);
	}
	li:last-child .row {
		border-bottom: 0;
	}
	a.row:hover .label {
		text-decoration: underline;
		text-underline-offset: 3px;
	}
	.labels,
	.values {
		display: grid;
		min-width: 0;
	}
	.values {
		text-align: right;
	}
	.label {
		font-weight: 550;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.value {
		font-weight: 600;
	}
	.sub {
		font-size: 12.5px;
		color: var(--text-3);
	}
	.track {
		grid-column: 1 / -1;
		height: 6px;
		border-radius: 999px;
		background: var(--surface-2);
		overflow: hidden;
	}
	.fill {
		height: 100%;
		border-radius: 999px;
		background: var(--accent-mark);
		min-width: 3px;
	}
	.empty {
		color: var(--text-3);
		padding: 16px 0;
	}
</style>
