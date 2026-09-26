<script lang="ts">
	interface Props {
		checked: boolean;
		label: string;
		disabled?: boolean;
		busy?: boolean;
		size?: 'md' | 'lg';
		onchange: (checked: boolean) => void;
	}
	let { checked, label, disabled = false, busy = false, size = 'md', onchange }: Props = $props();
</script>

<button
	type="button"
	role="switch"
	aria-checked={checked}
	aria-label={label}
	aria-busy={busy}
	class="switch {size}"
	class:busy
	{disabled}
	onclick={(e) => {
		e.preventDefault();
		e.stopPropagation();
		onchange(!checked);
	}}
>
	<span class="knob"></span>
</button>

<style>
	.switch {
		--w: 44px;
		--h: 26px;
		position: relative;
		flex: none;
		width: var(--w);
		height: var(--h);
		padding: 0;
		border: 0;
		border-radius: 999px;
		background: var(--surface-3);
		transition: background 0.2s;
	}
	.switch.lg {
		--w: 60px;
		--h: 34px;
	}
	/* Área de toque maior que o controle visível. */
	.switch::before {
		content: '';
		position: absolute;
		inset: -9px -6px;
	}
	.knob {
		position: absolute;
		top: 3px;
		left: 3px;
		width: calc(var(--h) - 6px);
		height: calc(var(--h) - 6px);
		border-radius: 50%;
		background: #fff;
		box-shadow: 0 1px 3px rgb(0 0 0 / 0.25);
		transition: transform 0.22s cubic-bezier(0.3, 1.3, 0.5, 1);
	}
	.switch[aria-checked='true'] {
		background: var(--accent);
	}
	.switch[aria-checked='true'] .knob {
		transform: translateX(calc(var(--w) - var(--h)));
	}
	.switch.busy .knob {
		animation: pulse 0.9s ease-in-out infinite;
	}
	.switch:disabled {
		opacity: 0.45;
		cursor: not-allowed;
	}
	@keyframes pulse {
		50% {
			opacity: 0.55;
		}
	}
</style>
