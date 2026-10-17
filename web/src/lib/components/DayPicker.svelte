<script lang="ts">
	import { ALL_DAYS, WEEKDAYS, WEEKDAY_INITIALS, WEEKEND, WORKDAYS } from '$lib/format';

	let { value = $bindable(ALL_DAYS) }: { value: number } = $props();
	const presets = [
		{ label: 'Todos os dias', days: ALL_DAYS },
		{ label: 'Dias úteis', days: WORKDAYS },
		{ label: 'Fins de semana', days: WEEKEND }
	];
	// Ordem de exibição começando na segunda-feira, como no calendário brasileiro de trabalho.
	const order = [1, 2, 3, 4, 5, 6, 0];

	function toggle(day: number) {
		const next = value ^ (1 << day);
		if (next) value = next; // pelo menos um dia
	}
</script>

<div class="days">
	<div class="chips" role="group" aria-label="Dias da semana">
		{#each order as day (day)}
			<button
				type="button"
				aria-pressed={!!(value & (1 << day))}
				aria-label={WEEKDAYS[day]}
				onclick={() => toggle(day)}
			>
				{WEEKDAY_INITIALS[day]}
			</button>
		{/each}
	</div>
	<div class="presets">
		{#each presets as preset (preset.days)}
			<button
				type="button"
				class="preset"
				class:active={value === preset.days}
				onclick={() => (value = preset.days)}
			>
				{preset.label}
			</button>
		{/each}
	</div>
</div>

<style>
	.days {
		display: grid;
		gap: 10px;
	}
	.chips {
		display: grid;
		grid-template-columns: repeat(7, 1fr);
		gap: 6px;
	}
	.chips button {
		height: 40px;
		border-radius: 10px;
		border: 1px solid var(--border-strong);
		background: var(--surface);
		font-weight: 600;
		font-size: 14px;
		color: var(--text-2);
	}
	.chips button[aria-pressed='true'] {
		background: var(--text);
		border-color: var(--text);
		color: var(--bg);
	}
	.presets {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
	}
	.preset {
		height: 28px;
		padding: 0 10px;
		border-radius: 999px;
		border: 1px solid var(--border);
		background: transparent;
		font-size: 12.5px;
		font-weight: 550;
		color: var(--text-2);
	}
	.preset.active {
		border-color: var(--text-2);
		color: var(--text);
	}
</style>
