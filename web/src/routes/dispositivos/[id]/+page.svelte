<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { ChevronLeft, Plus, RefreshCw, ShieldCheck, TriangleAlert } from '@lucide/svelte';
	import { api } from '$lib/api';
	import AreaChart from '$lib/components/AreaChart.svelte';
	import ColumnChart from '$lib/components/ColumnChart.svelte';
	import KindIcon from '$lib/components/KindIcon.svelte';
	import ScheduleForm from '$lib/components/ScheduleForm.svelte';
	import ScheduleRow from '$lib/components/ScheduleRow.svelte';
	import Sheet from '$lib/components/Sheet.svelte';
	import Switch from '$lib/components/Switch.svelte';
	import { pending, setPower } from '$lib/control.svelte';
	import { amps, bucketLabels, dateTime, kwh, kwhTick, money, relative, volts, watts, wattsParts, wattsTick } from '$lib/format';
	import { errorMessage, home, toast } from '$lib/state.svelte';
	import type { DeviceDetail, DeviceKind, Schedule } from '$lib/types';

	const id = $derived(Number(page.params.id));
	let detail = $state<DeviceDetail | null>(null);
	let notFound = $state(false);
	let refreshing = $state(false);
	let scheduleOpen = $state(false);
	let editing = $state<Schedule | null>(null);
	let removeOpen = $state(false);

	// Estado ao vivo vem do store compartilhado; o detalhe traz histórico e energia.
	const device = $derived(home.byId(id) ?? detail);

	async function load() {
		try {
			detail = await api.get<DeviceDetail>(`/devices/${id}`);
		} catch (e) {
			if ((e as { status?: number }).status === 404) notFound = true;
			else toast(errorMessage(e), 'error');
		}
	}

	$effect(() => {
		void id;
		void home.versions.energy;
		void home.versions.schedules;
		load();
	});

	// ---------------------------------------------------------------- configurações
	let form = $state({
		name: '',
		room_id: '' as string,
		kind: 'plug' as DeviceKind,
		nominal_watts: '' as string | number,
		power_alert_watts: '' as string | number,
		confirm_off: false,
		ip: '',
		protocol_version: '' as string
	});
	let formFor = $state<number | null>(null);
	let saving = $state(false);

	$effect(() => {
		if (!detail || formFor === detail.id) return;
		formFor = detail.id;
		form = {
			name: detail.name,
			room_id: detail.room_id == null ? '' : String(detail.room_id),
			kind: detail.kind,
			nominal_watts: detail.nominal_watts ?? '',
			power_alert_watts: detail.power_alert_watts ?? '',
			confirm_off: detail.confirm_off,
			ip: detail.info.ip ?? '',
			protocol_version: detail.info.protocol_version ? String(detail.info.protocol_version) : ''
		};
	});

	const numOrNull = (v: string | number) => (v === '' || v == null ? null : Number(v));

	async function save(event: SubmitEvent) {
		event.preventDefault();
		saving = true;
		try {
			const body: Record<string, unknown> = {
				name: form.name.trim(),
				room_id: form.room_id === '' ? null : Number(form.room_id),
				kind: form.kind,
				nominal_watts: numOrNull(form.nominal_watts),
				power_alert_watts: numOrNull(form.power_alert_watts),
				confirm_off: form.confirm_off
			};
			if (detail?.adapter === 'tuya') {
				body.ip = form.ip.trim();
				body.protocol_version = form.protocol_version ? Number(form.protocol_version) : null;
			}
			home.upsert(await api.patch(`/devices/${id}`, body));
			toast('Alterações salvas');
			load();
		} catch (e) {
			toast(errorMessage(e), 'error');
		} finally {
			saving = false;
		}
	}

	async function refresh() {
		refreshing = true;
		try {
			home.upsert(await api.post(`/devices/${id}/refresh`));
		} catch (e) {
			toast(errorMessage(e), 'error');
		} finally {
			refreshing = false;
		}
	}

	async function remove() {
		try {
			await api.del(`/devices/${id}`);
			home.devices = home.devices.filter((d) => d.id !== id);
			toast('Aparelho removido');
			goto('/');
		} catch (e) {
			toast(errorMessage(e), 'error');
		}
	}

	const eventText: Record<string, string> = {
		on: 'Ligado',
		off: 'Desligado',
		failed: 'Comando falhou',
		online: 'Voltou a responder',
		offline: 'Perdeu a conexão'
	};
	const sourceText: Record<string, string> = {
		user: 'pelo app',
		schedule: 'por rotina',
		room: 'pelo cômodo',
		device: 'no aparelho ou outro app',
		system: ''
	};

	const powerPoints = $derived((detail?.power_history ?? []).map((p) => ({ ts: p.ts, value: p.avg_w })));
	const dailyColumns = $derived(
		(detail?.energy.daily ?? []).map((p, i, all) => {
			const [label, tooltip] = bucketLabels(p.start, 'day');
			return { label, tooltip: i === all.length - 1 ? `${tooltip} (hoje)` : tooltip, value: p.kwh };
		})
	);
	const [pNum, pUnit] = $derived(wattsParts(device?.online ? device.power_w : null));
</script>

<svelte:head><title>{device?.name ?? 'Aparelho'} · Cordyhome</title></svelte:head>

<a class="back" href="/"><ChevronLeft size={18} /> Início</a>

{#if notFound}
	<p class="muted">Esse aparelho não existe mais.</p>
{:else if !device || !detail}
	<div class="skeleton" style="height: 180px"></div>
{:else}
	<header class="head">
		<span class="icon" class:on={device.online && device.is_on}><KindIcon kind={device.kind} size={24} /></span>
		<div class="title">
			<h1>{device.name}</h1>
			<p class="muted">
				{home.roomName(device.room_id)}
				{#if device.info.product_name}· {device.info.product_name}{/if}
				{#if device.confirm_off}· <span class="protected"><ShieldCheck size={14} /> Protegido</span>{/if}
			</p>
		</div>
		<Switch
			size="lg"
			checked={device.is_on === true}
			label="{device.is_on ? 'Desligar' : 'Ligar'} {device.name}"
			disabled={!device.online}
			busy={!!pending[device.id]}
			onchange={(v) => setPower(device, v)}
		/>
	</header>

	{#if !device.online}
		<div class="issue" role="status">
			<TriangleAlert size={18} />
			<div>
				<strong>Sem conexão</strong>
				<p>{device.last_error ?? 'O aparelho não respondeu.'} Visto por último {relative(device.last_seen)}.</p>
			</div>
			<button class="btn sm" type="button" onclick={refresh} disabled={refreshing}>
				<RefreshCw size={15} class={refreshing ? 'spin' : ''} /> Tentar agora
			</button>
		</div>
	{/if}

	<section class="readings card">
		<div class="reading main-reading">
			<span class="eyebrow">{device.power_estimated ? 'Potência estimada' : 'Potência'}</span>
			<p><span class="big">{pNum}</span><span class="unit">{pUnit}</span></p>
		</div>
		{#if device.info.has_energy_meter}
			<div class="reading">
				<span class="eyebrow">Tensão</span>
				<p class="mid num">{device.online ? volts(device.voltage_v) : '—'}</p>
			</div>
			<div class="reading">
				<span class="eyebrow">Corrente</span>
				<p class="mid num">{device.online ? amps(device.current_a) : '—'}</p>
			</div>
		{/if}
		<div class="reading">
			<span class="eyebrow">Hoje</span>
			<p class="mid">{money(detail.energy.today_cost)}</p>
			<span class="faint num small">{kwh(detail.energy.today_kwh)}</span>
		</div>
		<div class="reading">
			<span class="eyebrow">Este mês</span>
			<p class="mid">{money(detail.energy.month_cost)}</p>
			<span class="faint small">
				{detail.energy.projected_cost != null ? `Previsão ${money(detail.energy.projected_cost)}` : kwh(detail.energy.month_kwh)}
			</span>
		</div>
	</section>

	{#if !device.info.has_energy_meter && !device.nominal_watts}
		<p class="hint muted">
			Este aparelho não mede energia. Informe a potência nominal em <a href="#ajustes">Configurações</a> para estimar o consumo.
		</p>
	{/if}

	<section class="card block">
		<h2>Potência nas últimas 24 horas</h2>
		<AreaChart points={powerPoints} format={watts} tickFormat={wattsTick} height={200} ariaLabel="Potência de {device.name} nas últimas 24 horas" />
	</section>

	<section class="card block">
		<h2>Consumo diário</h2>
		<ColumnChart
			columns={dailyColumns}
			current={dailyColumns.length - 1}
			format={kwh}
			tickFormat={kwhTick}
			height={190}
			ariaLabel="Consumo diário de {device.name} nos últimos 30 dias"
		/>
	</section>

	<div class="two">
		<section class="card block">
			<div class="block-head">
				<h2>Rotinas</h2>
				<button class="btn sm" type="button" onclick={() => { editing = null; scheduleOpen = true; }}>
					<Plus size={15} /> Nova
				</button>
			</div>
			{#if detail.schedules.length === 0}
				<p class="faint empty">Nenhuma rotina. Crie uma para ligar ou desligar em horários fixos.</p>
			{:else}
				<ul class="list">
					{#each detail.schedules as s (s.id)}
						<ScheduleRow schedule={s} showDevice={false} onedit={(x) => { editing = x; scheduleOpen = true; }} onchange={load} />
					{/each}
				</ul>
			{/if}
		</section>

		<section class="card block">
			<h2>Histórico</h2>
			{#if detail.events.length === 0}
				<p class="faint empty">Nada registrado ainda.</p>
			{:else}
				<ol class="events">
					{#each detail.events as e, i (i)}
						<li>
							<span class="event-dot" data-action={e.action}></span>
							<span class="event-text">
								{eventText[e.action] ?? e.action}
								<span class="faint">{sourceText[e.source] ?? ''}</span>
								{#if e.detail}<span class="faint detail">{e.detail}</span>{/if}
							</span>
							<time class="faint num" datetime={new Date(e.ts * 1000).toISOString()}>{dateTime(e.ts)}</time>
						</li>
					{/each}
				</ol>
			{/if}
		</section>
	</div>

	<section class="card block" id="ajustes">
		<h2>Configurações</h2>
		<form class="settings" onsubmit={save}>
			<label class="field">
				<span>Nome</span>
				<input class="input" bind:value={form.name} required maxlength="60" />
			</label>
			<label class="field">
				<span>Cômodo</span>
				<select class="input" bind:value={form.room_id}>
					<option value="">Sem cômodo</option>
					{#each home.rooms as room (room.id)}<option value={String(room.id)}>{room.name}</option>{/each}
				</select>
			</label>
			<label class="field">
				<span>Tipo</span>
				<select class="input" bind:value={form.kind}>
					<option value="plug">Tomada</option>
					<option value="light">Iluminação</option>
					<option value="switch">Interruptor</option>
					<option value="other">Outro</option>
				</select>
			</label>
			{#if !device.info.has_energy_meter}
				<label class="field">
					<span>Potência nominal (W)</span>
					<input class="input" type="number" min="0" step="1" inputmode="numeric" bind:value={form.nominal_watts} placeholder="Ex.: 60" />
					<small>Usada para estimar o consumo quando ligado.</small>
				</label>
			{/if}
			<label class="field">
				<span>Alertar acima de (W)</span>
				<input class="input" type="number" min="0" step="1" inputmode="numeric" bind:value={form.power_alert_watts} placeholder="Sem limite" />
				<small>Gera um alerta se o consumo passar desse valor.</small>
			</label>
			<label class="check">
				<input type="checkbox" bind:checked={form.confirm_off} />
				<span>
					<strong>Proteger contra desligamento</strong>
					<small>Pede confirmação antes de desligar e fica de fora do "desligar tudo".</small>
				</span>
			</label>

			{#if device.adapter === 'tuya'}
				<details class="advanced">
					<summary>Avançado</summary>
					<div class="advanced-grid">
						<label class="field">
							<span>Endereço IP</span>
							<input class="input mono" bind:value={form.ip} placeholder="192.168.0.20" inputmode="decimal" />
						</label>
						<label class="field">
							<span>Protocolo Tuya</span>
							<select class="input" bind:value={form.protocol_version}>
								<option value="">Detectar</option>
								{#each ['3.1', '3.3', '3.4', '3.5'] as v (v)}<option value={v}>{v}</option>{/each}
							</select>
						</label>
					</div>
				</details>
			{/if}

			<div class="form-actions">
				<button class="btn danger ghost" type="button" onclick={() => (removeOpen = true)}>Remover aparelho</button>
				<button class="btn primary" type="submit" disabled={saving}>Salvar</button>
			</div>
		</form>
	</section>

	<ScheduleForm open={scheduleOpen} schedule={editing} deviceId={id} onclose={() => (scheduleOpen = false)} onsaved={load} />

	<Sheet open={removeOpen} title="Remover {device.name}?" onclose={() => (removeOpen = false)}>
		<p class="muted">O histórico de consumo e as rotinas deste aparelho serão apagados. A tomada continua funcionando normalmente e pode ser importada de novo.</p>
		{#snippet footer()}
			<button class="btn" type="button" onclick={() => (removeOpen = false)}>Cancelar</button>
			<button class="btn primary" type="button" onclick={remove}>Remover</button>
		{/snippet}
	</Sheet>
{/if}

<style>
	.back {
		display: inline-flex;
		align-items: center;
		gap: 2px;
		margin: 0 0 16px -4px;
		color: var(--text-2);
		font-weight: 550;
		font-size: 14px;
		text-decoration: none;
	}
	.head {
		display: flex;
		align-items: center;
		gap: 14px;
		margin-bottom: 20px;
	}
	.title {
		flex: 1;
		min-width: 0;
	}
	.title p {
		margin-top: 3px;
		font-size: 14px;
	}
	.protected {
		display: inline-flex;
		align-items: center;
		gap: 3px;
		vertical-align: -2px;
	}
	.icon {
		display: grid;
		place-items: center;
		flex: none;
		width: 48px;
		height: 48px;
		border-radius: 14px;
		background: var(--surface-2);
		color: var(--text-2);
	}
	.icon.on {
		background: var(--accent);
		color: var(--on-accent);
	}
	.issue {
		display: flex;
		align-items: flex-start;
		gap: 12px;
		padding: 14px 16px;
		margin-bottom: 12px;
		border-radius: var(--radius);
		background: var(--warning-soft);
		color: var(--warning);
	}
	.issue div {
		flex: 1;
	}
	.issue p {
		color: var(--text-2);
		font-size: 14px;
		margin-top: 2px;
	}
	.readings {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 18px 16px;
		padding: 20px;
	}
	.main-reading {
		grid-column: 1 / -1;
	}
	.reading p {
		margin-top: 4px;
	}
	.big {
		font-size: 44px;
		font-weight: 600;
		letter-spacing: -0.035em;
		line-height: 1;
	}
	.unit {
		font-size: 18px;
		font-weight: 550;
		color: var(--text-2);
		margin-left: 5px;
	}
	.mid {
		font-size: 20px;
		font-weight: 600;
		letter-spacing: -0.01em;
	}
	.small {
		font-size: 12.5px;
	}
	@media (min-width: 760px) {
		.readings {
			grid-template-columns: 1.6fr repeat(4, 1fr);
			align-items: end;
		}
		.main-reading {
			grid-column: auto;
		}
	}
	.hint {
		font-size: 14px;
		margin: 10px 4px 0;
	}
	.block {
		padding: 18px 20px;
		margin-top: 12px;
	}
	.block h2 {
		font-size: 15px;
		margin-bottom: 14px;
	}
	.block-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 4px;
	}
	.block-head h2 {
		margin: 0;
	}
	.two {
		display: grid;
		gap: 0 12px;
	}
	@media (min-width: 900px) {
		.two {
			grid-template-columns: 1fr 1fr;
			align-items: start;
		}
	}
	.list,
	.events {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.empty {
		font-size: 14px;
		padding: 8px 0 4px;
	}
	.events li {
		display: grid;
		grid-template-columns: 10px 1fr auto;
		gap: 12px;
		align-items: baseline;
		padding: 8px 0;
		font-size: 14px;
	}
	.event-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: var(--text-3);
		transform: translateY(-1px);
	}
	.event-dot[data-action='on'] {
		background: var(--accent-mark);
	}
	.event-dot[data-action='failed'],
	.event-dot[data-action='offline'] {
		background: var(--warning);
	}
	.detail {
		display: block;
		font-size: 12.5px;
	}
	time {
		font-size: 12.5px;
		white-space: nowrap;
	}
	.settings {
		display: grid;
		gap: 16px;
		max-width: 640px;
	}
	@media (min-width: 700px) {
		.settings {
			grid-template-columns: 1fr 1fr;
		}
		.settings .check,
		.settings .advanced,
		.settings .form-actions {
			grid-column: 1 / -1;
		}
	}
	.check {
		display: flex;
		gap: 12px;
		align-items: flex-start;
		padding: 12px 14px;
		border: 1px solid var(--border);
		border-radius: var(--radius);
		cursor: pointer;
	}
	.check input {
		width: 18px;
		height: 18px;
		margin-top: 2px;
		accent-color: var(--accent-mark);
	}
	.check span {
		display: grid;
		gap: 2px;
	}
	.check small {
		color: var(--text-3);
		font-size: 13px;
	}
	.advanced summary {
		cursor: pointer;
		font-weight: 550;
		color: var(--text-2);
		font-size: 14px;
	}
	.advanced-grid {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 12px;
		margin-top: 12px;
	}
	.mono {
		font-family: var(--mono);
		font-size: 14px;
	}
	.form-actions {
		display: flex;
		justify-content: space-between;
		gap: 8px;
		padding-top: 4px;
	}
	:global(.spin) {
		animation: spin 0.9s linear infinite;
	}
	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
</style>
