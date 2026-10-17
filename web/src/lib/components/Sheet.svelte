<script lang="ts">
	import { X } from '@lucide/svelte';
	import type { Snippet } from 'svelte';

	interface Props {
		open: boolean;
		title: string;
		onclose: () => void;
		children: Snippet;
		footer?: Snippet;
	}
	let { open, title, onclose, children, footer }: Props = $props();
	let dialog: HTMLDialogElement | undefined = $state();

	$effect(() => {
		if (!dialog) return;
		if (open && !dialog.open) dialog.showModal();
		if (!open && dialog.open) dialog.close();
	});
</script>

<!-- Diálogo nativo: foco preso, Esc fecha, acessível por padrão. Vira "bottom sheet" no celular. -->
<dialog
	bind:this={dialog}
	onclose={onclose}
	onclick={(e) => e.target === dialog && onclose()}
	aria-labelledby="sheet-title"
>
	<div class="panel">
		<header>
			<h2 id="sheet-title">{title}</h2>
			<button class="btn ghost icon sm" type="button" aria-label="Fechar" onclick={onclose}>
				<X size={18} />
			</button>
		</header>
		<div class="body">{@render children()}</div>
		{#if footer}<footer>{@render footer()}</footer>{/if}
	</div>
</dialog>

<style>
	dialog {
		padding: 0;
		border: 0;
		background: transparent;
		max-width: min(520px, calc(100vw - 32px));
		width: 100%;
		max-height: calc(100dvh - 48px);
		color: var(--text);
	}
	dialog::backdrop {
		background: var(--overlay);
		backdrop-filter: blur(2px);
	}
	dialog[open] {
		animation: rise 0.22s cubic-bezier(0.2, 0.9, 0.3, 1);
	}
	.panel {
		display: flex;
		flex-direction: column;
		max-height: calc(100dvh - 48px);
		background: var(--surface);
		border-radius: var(--radius-lg);
		border: 1px solid var(--border);
		box-shadow: var(--shadow-lg);
	}
	header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		padding: 16px 16px 4px 20px;
	}
	.body {
		padding: 12px 20px 20px;
		overflow-y: auto;
	}
	footer {
		display: flex;
		justify-content: flex-end;
		gap: 8px;
		padding: 14px 20px;
		border-top: 1px solid var(--border);
	}
	@media (max-width: 640px) {
		dialog {
			max-width: 100vw;
			margin: auto 0 0;
			max-height: 92dvh;
		}
		.panel {
			border-radius: 22px 22px 0 0;
			max-height: 92dvh;
			padding-bottom: env(safe-area-inset-bottom);
		}
		dialog[open] {
			animation: slide 0.26s cubic-bezier(0.2, 0.9, 0.3, 1);
		}
		footer > :global(.btn) {
			flex: 1;
		}
	}
	@keyframes rise {
		from {
			opacity: 0;
			transform: translateY(8px) scale(0.98);
		}
	}
	@keyframes slide {
		from {
			transform: translateY(100%);
		}
	}
</style>
