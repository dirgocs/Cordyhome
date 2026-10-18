<script lang="ts">
	import { AirVent, CircuitBoard, Cpu, Lightbulb, Plug, Power } from '@lucide/svelte';
	import type { DeviceKind } from '$lib/types';

	let { kind, size = 20 }: { kind: DeviceKind; size?: number } = $props();
	const icons = { plug: Plug, light: Lightbulb, switch: Power, relay: CircuitBoard, climate: AirVent, other: Cpu };
	const Icon = $derived(icons[kind] ?? Cpu);
</script>

<Icon {size} strokeWidth={1.75} aria-hidden="true" />
