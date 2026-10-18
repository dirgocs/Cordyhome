<script lang="ts">
	import { to } from '$lib/nav';
	import { WifiOff } from '@lucide/svelte';
	import { pending, setPower } from '$lib/control.svelte';
	import { watts } from '$lib/format';
	import type { Device } from '$lib/types';
	import KindIcon from './KindIcon.svelte';
	import Switch from './Switch.svelte';

	let { device }: { device: Device } = $props();
	const on = $derived(device.online && device.is_on === true);
	const busy = $derived(!!pending[device.id]);
</script>

<a class="tile" class:on class:offline={!device.online} href={to(`/dispositivos/${device.id}`)}>
	<div class="top">
		<span class="icon"><KindIcon kind={device.kind} /></span>
		<Switch
			checked={device.is_on === true}
			label="{device.is_on ? 'Desligar' : 'Ligar'} {device.name}"
			disabled={!device.online}
			{busy}
			onchange={(value) => setPower(device, value)}
		/>
	</div>
	<div class="name">{device.name}</div>
	<div class="status">
		{#if !device.online}
			<WifiOff size={14} aria-hidden="true" /> Sem conexão
		{:else if device.is_on}
			<span class="num">{watts(device.power_w)}</span>
			{#if device.power_estimated}<span class="faint">estimado</span>{/if}
			{#if device.state?.brightness != null}<span class="faint num">· {device.state.brightness}%</span>{/if}
		{:else}
			Desligado
		{/if}
	</div>
</a>

<style>
	.tile {
		display: grid;
		grid-template-rows: auto 1fr auto;
		gap: 2px;
		min-height: 124px;
		padding: 14px 14px 12px;
		border-radius: var(--radius-lg);
		border: 1px solid var(--border);
		background: var(--surface);
		text-decoration: none;
		transition:
			background 0.2s,
			border-color 0.2s,
			transform 0.12s;
	}
	.tile:hover {
		border-color: var(--border-strong);
	}
	.tile:active {
		transform: scale(0.985);
	}
	.tile.on {
		background: var(--accent-soft);
		border-color: var(--accent-soft-border);
	}
	.top {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		margin-bottom: 10px;
	}
	.icon {
		display: grid;
		place-items: center;
		width: 36px;
		height: 36px;
		border-radius: 10px;
		background: var(--surface-2);
		color: var(--text-2);
		transition:
			background 0.2s,
			color 0.2s;
	}
	.on .icon {
		background: var(--accent);
		color: var(--on-accent);
	}
	.name {
		font-weight: 580;
		line-height: 1.25;
		align-self: end;
		overflow-wrap: anywhere;
	}
	.status {
		display: flex;
		align-items: center;
		gap: 6px;
		font-size: 13.5px;
		color: var(--text-2);
	}
	.on .status {
		color: var(--accent-strong);
		font-weight: 550;
	}
	.offline .name,
	.offline .icon {
		opacity: 0.55;
	}
	.offline .status {
		color: var(--warning);
	}
</style>
