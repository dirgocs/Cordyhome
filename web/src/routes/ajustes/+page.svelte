<script lang="ts">
	import { goto } from '$app/navigation';
	import { ArrowDown, ArrowUp, Check, LogOut, Pencil, Plus, Radar, Trash2, X } from '@lucide/svelte';
	import { api } from '$lib/api';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Segmented from '$lib/components/Segmented.svelte';
	import Sheet from '$lib/components/Sheet.svelte';
	import { dateShort } from '$lib/format';
	import { errorMessage, home, session, toast } from '$lib/state.svelte';
	import { applyTheme, getTheme, type Theme } from '$lib/theme';
	import type { Room, Settings, TuyaStatus } from '$lib/types';

	let settings = $state<Settings | null>(null);
	let tuya = $state<TuyaStatus | null>(null);
	let timezones = $state<string[]>([]);
	let theme = $state<Theme>(getTheme());
	let tariff = $state('');
	let scanning = $state(false);
	let unlinkOpen = $state(false);

	async function load() {
		try {
			[settings, tuya] = await Promise.all([api.get<Settings>('/settings'), api.get<TuyaStatus>('/tuya')]);
			tariff = settings.tariff_per_kwh.toFixed(2).replace('.', ',');
		} catch (e) {
			toast(errorMessage(e), 'error');
		}
	}

	$effect(() => {
		load();
		api.get<string[]>('/timezones').then((t) => (timezones = t)).catch(() => {});
	});

	async function saveSettings(patch: Partial<Settings>) {
		try {
			settings = await api.patch<Settings>('/settings', patch);
			toast('Configuração salva');
		} catch (e) {
			toast(errorMessage(e), 'error');
		}
	}

	function saveTariff(event: SubmitEvent) {
		event.preventDefault();
		const value = Number(tariff.replace(/\./g, '').replace(',', '.'));
		if (!Number.isFinite(value) || value < 0) {
			toast('Informe um valor válido, por exemplo 0,85.', 'error');
			return;
		}
		saveSettings({ tariff_per_kwh: value });
	}

	async function rescan() {
		scanning = true;
		try {
			const res = await api.post<{ updated: number }>('/tuya/rescan');
			toast(res.updated ? `${res.updated} endereço(s) atualizado(s)` : 'Nenhuma mudança de endereço na rede');
		} catch (e) {
			toast(errorMessage(e), 'error');
		} finally {
			scanning = false;
		}
	}

	async function unlink() {
		try {
			await api.del('/tuya');
			unlinkOpen = false;
			toast('Conta Tuya desvinculada. As tomadas continuam funcionando.');
			load();
		} catch (e) {
			toast(errorMessage(e), 'error');
		}
	}

	// ------------------------------------------------------------------ cômodos
	let newRoom = $state('');
	let editingRoom = $state<number | null>(null);
	let roomName = $state('');
	let deletingRoom = $state<Room | null>(null);

	async function addRoom(event: SubmitEvent) {
		event.preventDefault();
		if (!newRoom.trim()) return;
		try {
			await api.post('/rooms', { name: newRoom.trim() });
			newRoom = '';
			home.rooms = await api.get<Room[]>('/rooms');
		} catch (e) {
			toast(errorMessage(e), 'error');
		}
	}

	async function renameRoom(event: SubmitEvent) {
		event.preventDefault();
		if (editingRoom == null || !roomName.trim()) return;
		try {
			await api.patch(`/rooms/${editingRoom}`, { name: roomName.trim() });
			editingRoom = null;
			home.rooms = await api.get<Room[]>('/rooms');
		} catch (e) {
			toast(errorMessage(e), 'error');
		}
	}

	async function moveRoom(index: number, delta: number) {
		const ids = home.rooms.map((r) => r.id);
		const [id] = ids.splice(index, 1);
		ids.splice(index + delta, 0, id);
		try {
			home.rooms = await api.put<Room[]>('/rooms/order', { ids });
		} catch (e) {
			toast(errorMessage(e), 'error');
		}
	}

	async function deleteRoom() {
		if (!deletingRoom) return;
		try {
			await api.del(`/rooms/${deletingRoom.id}`);
			deletingRoom = null;
			await home.refresh();
		} catch (e) {
			toast(errorMessage(e), 'error');
		}
	}

	async function logout() {
		await api.post('/auth/logout').catch(() => {});
		home.disconnect();
		session.user = null;
		goto('/entrar');
	}

	const deviceCount = (roomId: number) => home.devices.filter((d) => d.room_id === roomId).length;
</script>

<svelte:head><title>Ajustes · Cordyhome</title></svelte:head>

<PageHeader title="Ajustes" />

<div class="sections">
	<section class="card section">
		<div class="section-head">
			<div>
				<h2>Tomadas Tuya</h2>
				<p class="muted">
					{#if tuya?.linked}
						Conta vinculada{tuya.username ? ` (${tuya.username})` : ''}{tuya.linked_at ? ` em ${dateShort(tuya.linked_at * 1000)}` : ''} · {tuya.imported_devices} aparelhos importados
					{:else}
						Conecte a conta do app Tuya Smart / Smart Life para importar as tomadas. O controle depois é local.
					{/if}
				</p>
			</div>
		</div>
		<div class="actions">
			<a class="btn primary" href="/ajustes/tuya"><Plus size={16} /> {tuya?.linked ? 'Adicionar ou sincronizar' : 'Conectar conta'}</a>
			{#if tuya?.imported_devices}
				<button class="btn" type="button" onclick={rescan} disabled={scanning}>
					<Radar size={16} /> {scanning ? 'Procurando…' : 'Procurar na rede'}
				</button>
			{/if}
			{#if tuya?.linked}
				<button class="btn ghost danger" type="button" onclick={() => (unlinkOpen = true)}>Desvincular</button>
			{/if}
		</div>
	</section>

	<section class="card section">
		<h2>Cômodos</h2>
		<ul class="rooms">
			{#each home.rooms as room, i (room.id)}
				<li>
					{#if editingRoom === room.id}
						<form class="rename" onsubmit={renameRoom}>
							<!-- svelte-ignore a11y_autofocus -->
							<input class="input" bind:value={roomName} maxlength="40" aria-label="Nome do cômodo" autofocus />
							<button class="btn icon sm" type="submit" aria-label="Salvar nome"><Check size={16} /></button>
							<button class="btn icon sm ghost" type="button" aria-label="Cancelar" onclick={() => (editingRoom = null)}><X size={16} /></button>
						</form>
					{:else}
						<span class="room-name">{room.name}</span>
						<span class="faint count">{deviceCount(room.id)} {deviceCount(room.id) === 1 ? 'aparelho' : 'aparelhos'}</span>
						<div class="room-actions">
							<button class="btn ghost icon sm" type="button" aria-label="Mover {room.name} para cima" disabled={i === 0} onclick={() => moveRoom(i, -1)}><ArrowUp size={16} /></button>
							<button class="btn ghost icon sm" type="button" aria-label="Mover {room.name} para baixo" disabled={i === home.rooms.length - 1} onclick={() => moveRoom(i, 1)}><ArrowDown size={16} /></button>
							<button class="btn ghost icon sm" type="button" aria-label="Renomear {room.name}" onclick={() => { editingRoom = room.id; roomName = room.name; }}><Pencil size={16} /></button>
							<button class="btn ghost icon sm" type="button" aria-label="Excluir {room.name}" onclick={() => (deletingRoom = room)}><Trash2 size={16} /></button>
						</div>
					{/if}
				</li>
			{/each}
		</ul>
		<form class="add-room" onsubmit={addRoom}>
			<input class="input" bind:value={newRoom} placeholder="Novo cômodo, ex.: Varanda" maxlength="40" aria-label="Nome do novo cômodo" />
			<button class="btn" type="submit" disabled={!newRoom.trim()}><Plus size={16} /> Adicionar</button>
		</form>
	</section>

	<section class="card section">
		<h2>Tarifa de energia</h2>
		<p class="muted">
			Usada para calcular o custo. Na conta de luz, divida o valor total pelo consumo em kWh para
			incluir impostos e bandeira.
		</p>
		<form class="tariff" onsubmit={saveTariff}>
			<label class="field">
				<span>R$ por kWh</span>
				<div class="prefix">
					<span>R$</span>
					<input class="input num" bind:value={tariff} inputmode="decimal" aria-label="Tarifa em reais por kWh" />
				</div>
			</label>
			<button class="btn" type="submit">Salvar</button>
		</form>
	</section>

	<section class="card section">
		<h2>Sistema</h2>
		{#if settings}
			<div class="grid">
				<label class="field">
					<span>Fuso horário</span>
					<select class="input" value={settings.timezone} onchange={(e) => saveSettings({ timezone: e.currentTarget.value })}>
						{#each timezones.length ? timezones : [settings.timezone] as tz (tz)}<option value={tz}>{tz.replace(/_/g, ' ')}</option>{/each}
					</select>
					<small>Base para rotinas e relatórios.</small>
				</label>
				<label class="field">
					<span>Intervalo de leitura</span>
					<select class="input" value={String(settings.poll_interval_sec)} onchange={(e) => saveSettings({ poll_interval_sec: Number(e.currentTarget.value) })}>
						{#each [5, 10, 15, 30, 60] as s (s)}<option value={String(s)}>{s} segundos</option>{/each}
					</select>
					<small>Menor = mais preciso; maior = menos tráfego na rede.</small>
				</label>
			</div>
		{/if}
		<div class="field theme">
			<span>Aparência</span>
			<Segmented
				label="Aparência"
				value={theme}
				options={[
					{ value: 'system', label: 'Sistema' },
					{ value: 'light', label: 'Claro' },
					{ value: 'dark', label: 'Escuro' }
				]}
				onchange={(v) => {
					theme = v;
					applyTheme(v);
				}}
			/>
		</div>
	</section>

	<section class="card section">
		<h2>Conta</h2>
		<p class="muted">Conectado como <strong>{session.user?.username}</strong>.</p>
		<p class="muted small">
			Para acessar de fora de casa sem abrir portas no roteador, use o Tailscale (gratuito). O
			passo a passo está no README do projeto.
		</p>
		<div class="actions">
			<button class="btn" type="button" onclick={logout}><LogOut size={16} /> Sair</button>
		</div>
	</section>
</div>

<Sheet open={unlinkOpen} title="Desvincular conta Tuya?" onclose={() => (unlinkOpen = false)}>
	<p class="muted">
		As tomadas importadas continuam funcionando localmente. Você só precisará vincular de novo para
		importar tomadas novas ou atualizar chaves de tomadas pareadas outra vez.
	</p>
	{#snippet footer()}
		<button class="btn" type="button" onclick={() => (unlinkOpen = false)}>Cancelar</button>
		<button class="btn primary" type="button" onclick={unlink}>Desvincular</button>
	{/snippet}
</Sheet>

<Sheet open={deletingRoom !== null} title="Excluir {deletingRoom?.name ?? ''}?" onclose={() => (deletingRoom = null)}>
	<p class="muted">Os aparelhos deste cômodo não são apagados; eles ficam em "Sem cômodo".</p>
	{#snippet footer()}
		<button class="btn" type="button" onclick={() => (deletingRoom = null)}>Cancelar</button>
		<button class="btn primary" type="button" onclick={deleteRoom}>Excluir</button>
	{/snippet}
</Sheet>

<style>
	.sections {
		display: grid;
		gap: 12px;
		max-width: 760px;
	}
	.section {
		display: grid;
		gap: 14px;
		padding: 20px;
	}
	.section p {
		font-size: 14px;
		margin-top: 4px;
	}
	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
	}
	.rooms {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.rooms li {
		display: flex;
		align-items: center;
		gap: 10px;
		min-height: 48px;
		border-bottom: 1px solid var(--border);
	}
	.room-name {
		font-weight: 550;
	}
	.count {
		font-size: 13px;
	}
	.room-actions {
		margin-left: auto;
		display: flex;
	}
	.rename {
		display: flex;
		gap: 6px;
		width: 100%;
		padding: 6px 0;
	}
	.rename .input {
		height: 36px;
	}
	.add-room,
	.tariff {
		display: flex;
		gap: 8px;
		align-items: flex-end;
	}
	.add-room .input {
		flex: 1;
	}
	.prefix {
		position: relative;
	}
	.prefix span {
		position: absolute;
		left: 12px;
		top: 50%;
		transform: translateY(-50%);
		color: var(--text-3);
		font-weight: 550;
	}
	.prefix .input {
		padding-left: 40px;
		width: 150px;
	}
	.grid {
		display: grid;
		gap: 16px;
	}
	@media (min-width: 640px) {
		.grid {
			grid-template-columns: 1fr 1fr;
		}
	}
	.theme {
		justify-items: start;
	}
	.small {
		font-size: 13px !important;
	}
</style>
