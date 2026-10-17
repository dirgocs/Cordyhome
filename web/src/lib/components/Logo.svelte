<script lang="ts">
	let { size = 24 }: { size?: number } = $props();
</script>

<!-- Marca: um "C" aberto (o circuito) com o ponto de energia fechando o traço. -->
<svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
	<path
		d="M17.5 6.2A8 8 0 1 0 17.5 17.8"
		fill="none"
		stroke="currentColor"
		stroke-width="2.6"
		stroke-linecap="round"
	/>
	<circle cx="18.6" cy="12" r="2.6" fill="var(--accent)" />
</svg>
