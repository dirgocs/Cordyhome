<script lang="ts">
	import { answerConfirm, confirmation } from '$lib/control.svelte';
	import Sheet from './Sheet.svelte';
</script>

<Sheet
	open={confirmation.device !== null}
	title="Desligar {confirmation.device?.name ?? ''}?"
	onclose={() => answerConfirm(false)}
>
	<p class="muted">
		Este aparelho está marcado como protegido. Desligá-lo pode ter consequências (uma geladeira,
		por exemplo).
	</p>
	{#snippet footer()}
		<button class="btn" type="button" onclick={() => answerConfirm(false)}>Cancelar</button>
		<button class="btn primary" type="button" onclick={() => answerConfirm(true)}>Desligar</button>
	{/snippet}
</Sheet>
