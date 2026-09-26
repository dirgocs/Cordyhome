<script lang="ts" generics="T extends string">
	interface Props {
		options: { value: T; label: string }[];
		value: T;
		label: string;
		onchange: (value: T) => void;
	}
	let { options, value, label, onchange }: Props = $props();
</script>

<div class="segmented" role="radiogroup" aria-label={label}>
	{#each options as option (option.value)}
		<button
			type="button"
			role="radio"
			aria-checked={option.value === value}
			onclick={() => onchange(option.value)}
		>
			{option.label}
		</button>
	{/each}
</div>

<style>
	.segmented {
		display: inline-flex;
		gap: 2px;
		padding: 3px;
		border-radius: 11px;
		background: var(--surface-2);
		max-width: 100%;
		overflow-x: auto;
		scrollbar-width: none;
	}
	button {
		flex: none;
		height: 32px;
		padding: 0 12px;
		border: 0;
		border-radius: 8px;
		background: transparent;
		color: var(--text-2);
		font-size: 13.5px;
		font-weight: 550;
		white-space: nowrap;
	}
	button:hover {
		color: var(--text);
	}
	button[aria-checked='true'] {
		background: var(--surface);
		color: var(--text);
		box-shadow:
			0 1px 2px rgb(0 0 0 / 0.08),
			0 0 0 1px var(--border);
	}
</style>
