<script lang="ts">
	import { toasts } from '$lib/state.svelte';
</script>

<div class="toasts" role="status" aria-live="polite">
	{#each toasts as t (t.id)}
		<div class="toast" class:error={t.tone === 'error'}>{t.message}</div>
	{/each}
</div>

<style>
	.toasts {
		position: fixed;
		z-index: 100;
		left: 50%;
		bottom: calc(var(--tabbar) + 16px + env(safe-area-inset-bottom));
		transform: translateX(-50%);
		display: grid;
		gap: 8px;
		width: min(420px, calc(100vw - 32px));
		pointer-events: none;
	}
	@media (min-width: 900px) {
		.toasts {
			bottom: 24px;
			left: calc(50% + var(--sidebar) / 2);
		}
	}
	.toast {
		padding: 12px 16px;
		border-radius: 12px;
		background: var(--text);
		color: var(--bg);
		font-size: 14px;
		font-weight: 500;
		box-shadow: var(--shadow-lg);
		animation: in 0.2s ease-out;
	}
	.toast.error {
		background: var(--critical);
		color: #fff;
	}
	@keyframes in {
		from {
			opacity: 0;
			transform: translateY(6px);
		}
	}
</style>
