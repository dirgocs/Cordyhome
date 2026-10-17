<script lang="ts">
	import { api } from '$lib/api';
	import { ALL_DAYS } from '$lib/format';
	import { errorMessage, home, toast } from '$lib/state.svelte';
	import type { Action, Schedule } from '$lib/types';
	import DayPicker from './DayPicker.svelte';
	import Segmented from './Segmented.svelte';
	import Sheet from './Sheet.svelte';

	interface Props {
		open: boolean;
		/** Agendamento em edição; ausente = novo. */
		schedule?: Schedule | null;
		/** Fixa o aparelho (tela de detalhe). */
		deviceId?: number | null;
		onclose: () => void;
		onsaved?: () => void;
	}
	let { open, schedule = null, deviceId = null, onclose, onsaved }: Props = $props();

	let device = $state<number | null>(null);
	let action = $state<Action>('on');
	let time = $state('07:00');
	let days = $state(ALL_DAYS);
	let busy = $state(false);

	// Preenche o formulário toda vez que abre.
	$effect(() => {
		if (!open) return;
		device = schedule?.device_id ?? deviceId ?? home.devices[0]?.id ?? null;
		action = schedule?.action ?? 'on';
		time = schedule?.time ?? '07:00';
		days = schedule?.days ?? ALL_DAYS;
	});

	async function remove() {
		if (!schedule) return;
		busy = true;
		try {
			await api.del(`/schedules/${schedule.id}`);
			toast('Rotina removida');
			onsaved?.();
			onclose();
		} catch (e) {
			toast(errorMessage(e), 'error');
		} finally {
			busy = false;
		}
	}

	async function save(event: SubmitEvent) {
		event.preventDefault();
		if (device == null) return;
		busy = true;
		try {
			if (schedule) {
				await api.patch(`/schedules/${schedule.id}`, { action, time, days });
			} else {
				await api.post('/schedules', { device_id: device, action, time, days });
			}
			toast(schedule ? 'Rotina atualizada' : 'Rotina criada');
			onsaved?.();
			onclose();
		} catch (e) {
			toast(errorMessage(e), 'error');
		} finally {
			busy = false;
		}
	}
</script>

<Sheet {open} title={schedule ? 'Editar rotina' : 'Nova rotina'} {onclose}>
	<form id="schedule-form" class="form" onsubmit={save}>
		{#if deviceId == null && !schedule}
			<label class="field">
				<span>Aparelho</span>
				<select class="input" bind:value={device} required>
					{#each home.rooms as room (room.id)}
						{@const list = home.devices.filter((d) => d.room_id === room.id)}
						{#if list.length}
							<optgroup label={room.name}>
								{#each list as d (d.id)}<option value={d.id}>{d.name}</option>{/each}
							</optgroup>
						{/if}
					{/each}
					{#each home.devices.filter((d) => !home.rooms.some((r) => r.id === d.room_id)) as d (d.id)}
						<option value={d.id}>{d.name}</option>
					{/each}
				</select>
			</label>
		{/if}
		<div class="field">
			<span>Ação</span>
			<Segmented
				label="Ação"
				value={action}
				options={[
					{ value: 'on', label: 'Ligar' },
					{ value: 'off', label: 'Desligar' },
					{ value: 'toggle', label: 'Inverter' }
				]}
				onchange={(v) => (action = v)}
			/>
		</div>
		<label class="field">
			<span>Horário</span>
			<input class="input time" type="time" bind:value={time} required />
		</label>
		<div class="field">
			<span>Repetir</span>
			<DayPicker bind:value={days} />
		</div>
	</form>
	{#snippet footer()}
		{#if schedule}
			<button class="btn ghost danger remove" type="button" onclick={remove} disabled={busy}>Remover</button>
		{/if}
		<button class="btn" type="button" onclick={onclose}>Cancelar</button>
		<button class="btn primary" type="submit" form="schedule-form" disabled={busy}>
			{schedule ? 'Salvar' : 'Criar rotina'}
		</button>
	{/snippet}
</Sheet>

<style>
	.remove {
		margin-right: auto;
	}
	.form {
		display: grid;
		gap: 20px;
	}
	.time {
		font-size: 22px;
		font-weight: 600;
		height: 52px;
		width: 160px;
		font-variant-numeric: tabular-nums;
	}
</style>
