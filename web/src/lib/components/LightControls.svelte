<script lang="ts">
	import { setState } from '$lib/control.svelte';
	import type { Device, Hsv } from '$lib/types';

	let { device }: { device: Device } = $props();

	const caps = $derived(new Set(device.capabilities ?? []));
	const visible = $derived(caps.has('brightness') || caps.has('color_temp') || caps.has('color'));
	const colourMode = $derived(device.state?.mode === 'colour');
	const disabled = $derived(!device.online);

	// Valor mostrado enquanto o controle é arrastado; o comando vai ao soltar.
	let draft = $state<{ brightness?: number; color_temp?: number; hue?: number }>({});
	const brightness = $derived(draft.brightness ?? device.state?.brightness ?? 100);
	const colorTemp = $derived(draft.color_temp ?? device.state?.color_temp ?? 50);
	const color = $derived<Hsv>(device.state?.color ?? { h: 30, s: 100, v: 100 });
	const hue = $derived(draft.hue ?? color.h);

	const SWATCHES = [
		{ h: 0, label: 'Vermelho' },
		{ h: 25, label: 'Laranja' },
		{ h: 50, label: 'Amarelo' },
		{ h: 120, label: 'Verde' },
		{ h: 185, label: 'Ciano' },
		{ h: 225, label: 'Azul' },
		{ h: 275, label: 'Roxo' },
		{ h: 320, label: 'Rosa' }
	];

	async function send(changes: Parameters<typeof setState>[1]) {
		await setState(device, changes);
		draft = {};
	}

	function pickColor(h: number) {
		send({ color: { h, s: 100, v: Math.max(1, color.v) } });
	}
</script>

{#if visible}
	<section class="card controls" aria-label="Controles de luz">
		{#if caps.has('brightness')}
			<label class="control">
				<span class="label">Brilho <span class="num faint">{brightness}%</span></span>
				<input
					type="range"
					class="track brightness"
					min="1"
					max="100"
					value={brightness}
					{disabled}
					oninput={(e) => (draft.brightness = e.currentTarget.valueAsNumber)}
					onchange={(e) => send({ brightness: e.currentTarget.valueAsNumber })}
				/>
			</label>
		{/if}

		{#if caps.has('color_temp')}
			<label class="control" class:inactive={colourMode}>
				<span class="label">Tom do branco <span class="faint">{colorTemp < 34 ? 'quente' : colorTemp > 66 ? 'frio' : 'neutro'}</span></span>
				<input
					type="range"
					class="track temp"
					min="0"
					max="100"
					value={colorTemp}
					{disabled}
					oninput={(e) => (draft.color_temp = e.currentTarget.valueAsNumber)}
					onchange={(e) => send({ color_temp: e.currentTarget.valueAsNumber })}
				/>
			</label>
		{/if}

		{#if caps.has('color')}
			<div class="control" class:inactive={!colourMode && (caps.has('brightness') || caps.has('color_temp'))}>
				<span class="label">Cor</span>
				<div class="swatches" role="group" aria-label="Cores">
					{#each SWATCHES as swatch (swatch.h)}
						<button
							type="button"
							class="swatch"
							class:selected={colourMode && Math.abs(color.h - swatch.h) < 8}
							style="--c: hsl({swatch.h} 100% 50%)"
							aria-label={swatch.label}
							title={swatch.label}
							{disabled}
							onclick={() => pickColor(swatch.h)}
						></button>
					{/each}
				</div>
				<input
					type="range"
					class="track hue"
					min="0"
					max="360"
					value={hue}
					aria-label="Matiz"
					{disabled}
					oninput={(e) => (draft.hue = e.currentTarget.valueAsNumber)}
					onchange={(e) => pickColor(e.currentTarget.valueAsNumber)}
				/>
			</div>
		{/if}
	</section>
{/if}

<style>
	.controls {
		display: grid;
		gap: 18px;
		padding: 18px 20px;
		margin-bottom: 16px;
	}
	.control {
		display: grid;
		gap: 10px;
	}
	.inactive {
		opacity: 0.55;
	}
	.label {
		display: flex;
		justify-content: space-between;
		font-weight: 550;
		font-size: 14px;
	}
	.track {
		appearance: none;
		-webkit-appearance: none;
		width: 100%;
		height: 12px;
		border-radius: 999px;
		margin: 6px 0;
		background: var(--g);
		cursor: pointer;
	}
	.track:disabled {
		cursor: not-allowed;
		opacity: 0.5;
	}
	.track::-webkit-slider-thumb {
		-webkit-appearance: none;
		width: 24px;
		height: 24px;
		border-radius: 50%;
		background: #fff;
		border: 2px solid rgb(0 0 0 / 0.25);
		box-shadow: 0 1px 4px rgb(0 0 0 / 0.35);
	}
	.track::-moz-range-thumb {
		width: 22px;
		height: 22px;
		border-radius: 50%;
		background: #fff;
		border: 2px solid rgb(0 0 0 / 0.25);
		box-shadow: 0 1px 4px rgb(0 0 0 / 0.35);
	}
	.brightness {
		--g: linear-gradient(90deg, #3a3a36, #fff6d8);
	}
	.temp {
		--g: linear-gradient(90deg, #ffb066, #fff4e0 50%, #cfe2ff);
	}
	.hue {
		--g: linear-gradient(90deg, #f00, #ff0 17%, #0f0 33%, #0ff 50%, #00f 67%, #f0f 83%, #f00);
	}
	.swatches {
		display: flex;
		flex-wrap: wrap;
		gap: 10px;
	}
	.swatch {
		width: 32px;
		height: 32px;
		border-radius: 50%;
		border: 2px solid transparent;
		background: var(--c);
		box-shadow: inset 0 0 0 1px rgb(0 0 0 / 0.15);
		cursor: pointer;
		padding: 0;
	}
	.swatch.selected {
		border-color: var(--text);
		box-shadow:
			inset 0 0 0 2px var(--surface),
			0 0 0 1px var(--border);
	}
	.swatch:disabled {
		cursor: not-allowed;
		opacity: 0.5;
	}
</style>
