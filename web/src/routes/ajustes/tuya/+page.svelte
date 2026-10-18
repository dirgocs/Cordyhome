<script lang="ts">
	// Endereço antigo da conexão Tuya: agora fica em Adicionar aparelhos.
	import { goto } from '$app/navigation';
	import { to } from '$lib/nav';

	$effect(() => {
		goto(to('/adicionar/tuya'), { replaceState: true });
	});
</script>
