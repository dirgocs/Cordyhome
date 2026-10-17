<script lang="ts">
	import { api } from '$lib/api';
	import { daysLabel, nextRunLabel } from '$lib/format';
	import { errorMessage, toast } from '$lib/state.svelte';
	import type { Schedule } from '$lib/types';
	import Switch from './Switch.svelte';

	interface Props {
		schedule: Schedule;
		showDevice?: boolean;
		onedit: (s: Schedule) => void;
		onchange: () => void;
	}
	let { schedule, showDevice = true, onedit, onchange }: Props = $props();
	const verbs = { on: 'Liga', off: 'Desliga', toggle: 'Inverte' };

	async function setEnabled(enabled: boolean) {
		try {
			await api.patch(`/schedules/${schedule.id}`, { enabled });
			onchange();
		} catch (e) {
			toast(errorMessage(e), 'error');
		}
	}

</script>

<li class="row" class:paused={!schedule.enabled}>
	<button class="main" type="button" onclick={() => onedit(schedule)} aria-label="Editar rotina das {schedule.time}">
		<span class="time num">{schedule.time}</span>
		<span class="text">
			<span class="what">
				<span class="pill" class:accent={schedule.action === 'on'}>{verbs[schedule.action]}</span>
				{#if showDevice}<span class="device">{schedule.device_name}</span>{/if}
			</span>
			<span class="when faint">
				{daysLabel(schedule.days)}{schedule.enabled ? ` · ${nextRunLabel(schedule.next_run)}` : ''}
				{#if schedule.last_result && schedule.last_result !== 'ok'}
					· <span class="failed">Última execução falhou</span>
				{/if}
			</span>
		</span>
	</button>
	<Switch checked={schedule.enabled} label="Rotina ativa" onchange={setEnabled} />
</li>

<style>
	.row {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 12px 0;
		border-bottom: 1px solid var(--border);
	}
	.row:last-child {
		border-bottom: 0;
	}
	.main {
		flex: 1;
		min-width: 0;
		display: flex;
		align-items: center;
		gap: 16px;
		padding: 0;
		border: 0;
		background: none;
		text-align: left;
	}
	.time {
		font-size: 26px;
		font-weight: 600;
		letter-spacing: -0.02em;
		min-width: 76px;
	}
	.text {
		display: grid;
		gap: 3px;
		min-width: 0;
	}
	.what {
		display: flex;
		align-items: center;
		gap: 8px;
		min-width: 0;
	}
	.device {
		font-weight: 560;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.when {
		font-size: 13px;
	}
	.failed {
		color: var(--warning);
	}
	.paused .time,
	.paused .what {
		opacity: 0.45;
	}
	@media (max-width: 560px) {
		.time {
			font-size: 22px;
			min-width: 64px;
		}
		.main {
			gap: 12px;
		}
	}
</style>
