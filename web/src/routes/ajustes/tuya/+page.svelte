<script lang="ts">
	import { to } from '$lib/nav';
	import { goto } from '$app/navigation';
	import { Check, ChevronLeft, Gauge, LoaderCircle, RefreshCw, Smartphone, WifiOff } from '@lucide/svelte';
	import { onDestroy } from 'svelte';
	import { api } from '$lib/api';
	import { errorMessage, home, toast } from '$lib/state.svelte';
	import type { TuyaCandidate, TuyaStatus } from '$lib/types';

	type Step = 'code' | 'qr' | 'loading' | 'select' | 'done';

	let step = $state<Step>('code');
	let userCode = $state('');
	let qrSvg = $state('');
	let token = $state('');
	let busy = $state(false);
	let error = $state('');
	let expired = $state(false);
	let candidates = $state<TuyaCandidate[]>([]);
	let selected = $state<Record<string, boolean>>({});
	let importedCount = $state(0);
	let pollTimer: ReturnType<typeof setTimeout> | undefined;
	let pollStarted = 0;

	const isTouch = typeof window !== 'undefined' && window.matchMedia('(pointer: coarse)').matches;

	$effect(() => {
		api.get<TuyaStatus>('/tuya').then((s) => {
			if (s.linked) loadDevices();
		});
	});

	onDestroy(() => clearTimeout(pollTimer));

	async function startLogin(event?: SubmitEvent) {
		event?.preventDefault();
		error = '';
		busy = true;
		try {
			const res = await api.post<{ token: string; qr_svg: string }>('/tuya/login', { user_code: userCode.trim() });
			token = res.token;
			qrSvg = res.qr_svg;
			expired = false;
			step = 'qr';
			pollStarted = Date.now();
			poll();
		} catch (e) {
			error = errorMessage(e);
		} finally {
			busy = false;
		}
	}

	async function poll() {
		clearTimeout(pollTimer);
		if (Date.now() - pollStarted > 4.5 * 60_000) {
			expired = true;
			return;
		}
		try {
			const res = await api.get<{ linked: boolean }>(`/tuya/login/${encodeURIComponent(token)}`);
			if (res.linked) {
				loadDevices();
				return;
			}
		} catch (e) {
			expired = true;
			error = errorMessage(e);
			return;
		}
		pollTimer = setTimeout(poll, 2000);
	}

	async function loadDevices() {
		step = 'loading';
		error = '';
		try {
			candidates = await api.get<TuyaCandidate[]>('/tuya/devices');
			selected = Object.fromEntries(
				candidates.map((c) => [c.id, c.local_supported && c.imported_device_id == null])
			);
			step = 'select';
		} catch (e) {
			error = errorMessage(e);
			step = 'code';
		}
	}

	const groups = $derived.by(() => {
		const map = new Map<string, TuyaCandidate[]>();
		for (const c of candidates) {
			const key = c.room ?? 'Sem cômodo';
			map.set(key, [...(map.get(key) ?? []), c]);
		}
		return [...map.entries()];
	});
	const chosen = $derived(candidates.filter((c) => selected[c.id]));
	const newCount = $derived(chosen.filter((c) => c.imported_device_id == null).length);
	const missingIp = $derived(chosen.filter((c) => !c.lan_ip).length);

	function toggleAll(value: boolean) {
		selected = Object.fromEntries(candidates.map((c) => [c.id, value && c.local_supported]));
	}

	async function importSelected() {
		busy = true;
		try {
			const res = await api.post<{ imported: number[] }>('/tuya/import', {
				devices: chosen.map((c) => ({ id: c.id, room: c.room }))
			});
			importedCount = res.imported.length;
			await home.refresh();
			step = 'done';
		} catch (e) {
			toast(errorMessage(e), 'error');
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head><title>Conectar tomadas Tuya · Cordyhome</title></svelte:head>

<a class="back" href={to('/ajustes')}><ChevronLeft size={18} /> Ajustes</a>

<div class="wizard">
	<ol class="progress" aria-label="Etapas">
		{#each [['code', 'Conta'], ['qr', 'Autorizar'], ['select', 'Tomadas']] as [key, label], i (key)}
			{@const order = ['code', 'qr', 'loading', 'select', 'done']}
			{@const done = order.indexOf(step) > order.indexOf(key)}
			<li class:current={step === key || (key === 'select' && step === 'loading')} class:done>
				<span class="n">{#if done}<Check size={13} strokeWidth={3} />{:else}{i + 1}{/if}</span>{label}
			</li>
		{/each}
	</ol>

	{#if step === 'code'}
		<section class="card panel">
			<h1>Conectar tomadas Tuya</h1>
			<p class="muted lead">
				O Cordyhome usa sua conta do app só uma vez, para buscar as tomadas e as chaves de acesso local.
				Depois disso tudo funciona pela rede de casa, sem nuvem. Não precisa de conta de desenvolvedor.
			</p>

			<div class="how">
				<h2>Onde encontrar o código de usuário</h2>
				<ol>
					<li>Abra o app <strong>Tuya Smart</strong> (ou Smart Life) no celular.</li>
					<li>Toque em <strong>Eu</strong> e depois no ícone de <strong>configurações</strong> (engrenagem).</li>
					<li>Entre em <strong>Conta e segurança</strong> e copie o <strong>Código de usuário</strong>.</li>
				</ol>
			</div>

			<form class="code-form" onsubmit={startLogin}>
				<label class="field">
					<span>Código de usuário</span>
					<input class="input mono" bind:value={userCode} placeholder="Ex.: 3fK9aQ" autocomplete="off" autocapitalize="none" spellcheck="false" required minlength="4" />
				</label>
				{#if error}<p class="error" role="alert">{error}</p>{/if}
				<button class="btn primary" type="submit" disabled={busy || userCode.trim().length < 4}>
					{#if busy}<LoaderCircle size={16} class="spin" />{/if} Continuar
				</button>
			</form>
		</section>
	{:else if step === 'qr'}
		<section class="card panel qr-panel">
			<div class="qr-copy">
				<h1>Escaneie com o app</h1>
				<ol class="steps">
					<li>No app Tuya Smart, abra a aba <strong>Eu</strong>.</li>
					<li>Toque no ícone de <strong>leitura</strong> no canto superior direito.</li>
					<li>Aponte para o QR code e confirme a autorização.</li>
				</ol>
				<p class="faint note">
					O app vai mostrar "Home Assistant": é o nome do serviço oficial de compartilhamento da Tuya que o
					Cordyhome usa. O Cordyhome só lê a lista de aparelhos e as chaves de acesso local.
				</p>
				{#if isTouch}
					<p class="mobile-note"><Smartphone size={16} /> Está neste celular? Abra esta página no computador, ou escaneie a tela de outro aparelho.</p>
				{/if}
			</div>
			<div class="qr-box" class:expired>
				<!-- SVG gerado pelo próprio hub (segno), não vem de terceiros. -->
				<div class="qr">{@html qrSvg}</div>
				{#if expired}
					<div class="qr-expired">
						<p>{error || 'O QR code expirou.'}</p>
						<button class="btn sm" type="button" onclick={() => startLogin()}><RefreshCw size={15} /> Gerar outro</button>
					</div>
				{:else}
					<p class="waiting faint"><LoaderCircle size={15} class="spin" /> Aguardando confirmação…</p>
				{/if}
			</div>
		</section>
		<button class="btn ghost" type="button" onclick={() => { clearTimeout(pollTimer); step = 'code'; }}>Voltar</button>
	{:else if step === 'loading'}
		<section class="card panel center">
			<LoaderCircle size={28} class="spin" />
			<h2>Buscando suas tomadas</h2>
			<p class="muted">Lendo a conta e procurando cada tomada na rede local. Leva de 10 a 30 segundos.</p>
		</section>
	{:else if step === 'select'}
		<section class="card panel">
			<div class="select-head">
				<div>
					<h1>Escolha as tomadas</h1>
					<p class="muted">{candidates.length} encontradas na sua conta.</p>
				</div>
				<div class="select-actions">
					<button class="btn sm ghost" type="button" onclick={() => toggleAll(true)}>Todas</button>
					<button class="btn sm ghost" type="button" onclick={() => toggleAll(false)}>Nenhuma</button>
				</div>
			</div>

			{#each groups as [room, list] (room)}
				<h2 class="eyebrow group-title">{room}</h2>
				<ul class="candidates">
					{#each list as c (c.id)}
						<li>
							<label class:disabled={!c.local_supported}>
								<input type="checkbox" bind:checked={selected[c.id]} disabled={!c.local_supported} />
								<span class="c-main">
									<span class="c-name">{c.name}</span>
									<span class="c-meta">
										{#if c.has_energy_meter}<span class="pill accent"><Gauge size={12} /> Mede energia</span>{/if}
										{#if c.imported_device_id != null}<span class="pill">Já importada · atualizar</span>{/if}
										{#if !c.local_supported}
											<span class="pill critical">Sem controle local</span>
										{:else if !c.lan_ip}
											<span class="pill warning"><WifiOff size={12} /> Não achada na rede</span>
										{:else}
											<span class="faint mono ip">{c.lan_ip}</span>
										{/if}
									</span>
								</span>
							</label>
						</li>
					{/each}
				</ul>
			{/each}

			{#if missingIp > 0}
				<p class="hint muted">
					{missingIp} {missingIp === 1 ? 'tomada não respondeu' : 'tomadas não responderam'} na rede agora. Elas serão importadas e o
					Cordyhome continua procurando; confira se estão energizadas e no mesmo Wi-Fi do hub.
				</p>
			{/if}
		</section>
		<div class="sticky-footer">
			<button class="btn primary big" type="button" disabled={busy || chosen.length === 0} onclick={importSelected}>
				{#if busy}<LoaderCircle size={16} class="spin" />{/if}
				{newCount > 0 ? `Importar ${newCount} ${newCount === 1 ? 'tomada' : 'tomadas'}` : chosen.length ? 'Atualizar selecionadas' : 'Selecione tomadas'}
			</button>
		</div>
	{:else if step === 'done'}
		<section class="card panel center">
			<span class="done-icon"><Check size={26} strokeWidth={2.4} /></span>
			<h1>Pronto</h1>
			<p class="muted">{importedCount} {importedCount === 1 ? 'tomada conectada' : 'tomadas conectadas'}. As leituras de consumo começam agora.</p>
			<button class="btn primary" type="button" onclick={() => goto(to('/'))}>Ir para o início</button>
		</section>
	{/if}
</div>

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
	.wizard {
		max-width: 720px;
		display: grid;
		gap: 16px;
	}
	.progress {
		list-style: none;
		display: flex;
		gap: 20px;
		margin: 0;
		padding: 0;
		font-size: 13.5px;
		font-weight: 550;
		color: var(--text-3);
	}
	.progress li {
		display: flex;
		align-items: center;
		gap: 8px;
	}
	.n {
		display: grid;
		place-items: center;
		width: 22px;
		height: 22px;
		border-radius: 50%;
		border: 1.5px solid currentColor;
		font-size: 12px;
	}
	.progress .current {
		color: var(--text);
	}
	.progress .current .n {
		background: var(--text);
		border-color: var(--text);
		color: var(--bg);
	}
	.progress .done {
		color: var(--text-2);
	}
	.progress .done .n {
		background: var(--accent);
		border-color: var(--accent);
		color: var(--on-accent);
	}
	.panel {
		padding: 24px;
		display: grid;
		gap: 16px;
	}
	.lead {
		max-width: 560px;
	}
	.how {
		padding: 16px 18px;
		border-radius: var(--radius);
		background: var(--surface-2);
	}
	.how h2 {
		font-size: 14px;
		margin-bottom: 8px;
	}
	.how ol,
	.steps {
		margin: 0;
		padding-left: 20px;
		display: grid;
		gap: 6px;
		font-size: 14.5px;
	}
	.code-form {
		display: grid;
		gap: 12px;
		max-width: 360px;
	}
	.mono {
		font-family: var(--mono);
	}
	.error {
		color: var(--critical);
		font-size: 14px;
	}
	.qr-panel {
		grid-template-columns: 1fr;
		align-items: center;
	}
	@media (min-width: 720px) {
		.qr-panel {
			grid-template-columns: 1fr auto;
			gap: 32px;
		}
	}
	.qr-copy {
		display: grid;
		gap: 14px;
	}
	.note {
		font-size: 13px;
	}
	.mobile-note {
		display: flex;
		gap: 8px;
		align-items: flex-start;
		padding: 10px 12px;
		border-radius: var(--radius-sm);
		background: var(--warning-soft);
		color: var(--warning);
		font-size: 13.5px;
	}
	.qr-box {
		position: relative;
		display: grid;
		justify-items: center;
		gap: 12px;
	}
	.qr {
		width: 232px;
		height: 232px;
		padding: 10px;
		border-radius: 16px;
		background: #fff;
		border: 1px solid var(--border);
	}
	.qr :global(svg) {
		width: 100%;
		height: 100%;
	}
	.expired .qr {
		opacity: 0.12;
	}
	.qr-expired {
		position: absolute;
		top: 70px;
		display: grid;
		justify-items: center;
		gap: 10px;
		text-align: center;
		font-size: 14px;
		max-width: 220px;
	}
	.waiting {
		display: flex;
		align-items: center;
		gap: 6px;
		font-size: 13.5px;
	}
	.center {
		justify-items: center;
		text-align: center;
		padding: 48px 24px;
	}
	.select-head {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 12px;
	}
	.select-actions {
		display: flex;
		gap: 4px;
	}
	.group-title {
		margin-top: 8px;
	}
	.candidates {
		list-style: none;
		margin: -8px 0 0;
		padding: 0;
	}
	.candidates label {
		display: flex;
		gap: 14px;
		align-items: center;
		padding: 12px 0;
		border-bottom: 1px solid var(--border);
		cursor: pointer;
	}
	.candidates li:last-child label {
		border-bottom: 0;
	}
	.candidates input {
		width: 20px;
		height: 20px;
		flex: none;
		accent-color: var(--accent-mark);
	}
	.disabled {
		opacity: 0.6;
		cursor: not-allowed !important;
	}
	.c-main {
		display: grid;
		gap: 4px;
		min-width: 0;
	}
	.c-name {
		font-weight: 560;
	}
	.c-meta {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
		align-items: center;
	}
	.ip {
		font-size: 12.5px;
	}
	.hint {
		font-size: 13.5px;
	}
	.sticky-footer {
		position: sticky;
		bottom: calc(var(--tabbar) + 12px + env(safe-area-inset-bottom));
		display: flex;
		justify-content: flex-end;
	}
	@media (min-width: 900px) {
		.sticky-footer {
			bottom: 24px;
		}
	}
	.big {
		height: 48px;
		padding: 0 22px;
		box-shadow: var(--shadow-lg);
	}
	@media (max-width: 560px) {
		.big {
			width: 100%;
		}
	}
	.done-icon {
		display: grid;
		place-items: center;
		width: 56px;
		height: 56px;
		border-radius: 50%;
		background: var(--accent);
		color: var(--on-accent);
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
