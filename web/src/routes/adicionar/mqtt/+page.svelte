<script lang="ts">
	import { to } from '$lib/nav';
	import { goto } from '$app/navigation';
	import { Check, ChevronLeft, Copy, Gauge, KeyRound, LoaderCircle, Plug, Server } from '@lucide/svelte';
	import { onDestroy, onMount } from 'svelte';
	import { api } from '$lib/api';
	import KindIcon from '$lib/components/KindIcon.svelte';
	import { errorMessage, home, toast } from '$lib/state.svelte';
	import type { MqttCandidate, MqttStatus } from '$lib/types';

	let status = $state<MqttStatus | null>(null);
	let candidates = $state<MqttCandidate[]>([]);
	let selected = $state<Record<string, boolean>>({});
	let busy = $state(false);
	let error = $state('');
	let importedCount = $state<number | null>(null);
	let pollTimer: ReturnType<typeof setTimeout> | undefined;

	// Formulário de ativação.
	let mode = $state<'embedded' | 'external'>('embedded');
	let host = $state('');
	let port = $state(1883);
	let username = $state('');
	let password = $state('');

	onMount(refresh);
	onDestroy(() => clearTimeout(pollTimer));

	async function refresh() {
		clearTimeout(pollTimer);
		try {
			status = await api.get<MqttStatus>('/mqtt');
			if (status.enabled) {
				const list = await api.get<MqttCandidate[]>('/mqtt/devices');
				for (const c of list) {
					// Aparelho novo na lista: já vem marcado.
					if (!(c.id in selected)) selected[c.id] = c.imported_device_id == null;
				}
				candidates = list;
				// Os aparelhos aparecem conforme se conectam: a lista se atualiza sozinha.
				pollTimer = setTimeout(refresh, 3000);
			}
		} catch (e) {
			error = errorMessage(e);
		}
	}

	async function enable(event: SubmitEvent) {
		event.preventDefault();
		busy = true;
		error = '';
		try {
			const body =
				mode === 'embedded'
					? { enabled: true, mode, port }
					: { enabled: true, mode, host: host.trim(), port, username: username.trim(), password };
			status = await api.put<MqttStatus>('/mqtt', body);
			refresh();
		} catch (e) {
			error = errorMessage(e);
		} finally {
			busy = false;
		}
	}

	async function newPassword() {
		try {
			status = await api.post<MqttStatus>('/mqtt/password');
			toast('Senha nova gerada. Digite-a de novo nos aparelhos que já estavam conectados.');
		} catch (e) {
			toast(errorMessage(e), 'error');
		}
	}

	async function disable() {
		try {
			await api.del('/mqtt');
			candidates = [];
			selected = {};
			await refresh();
			toast('MQTT desativado. Os aparelhos MQTT ficam sem conexão até você ativar de novo.');
		} catch (e) {
			toast(errorMessage(e), 'error');
		}
	}

	async function copy(text: string) {
		try {
			await navigator.clipboard.writeText(text);
			toast('Copiado.');
		} catch {
			toast('Não consegui copiar. Selecione e copie à mão.', 'error');
		}
	}

	const chosen = $derived(candidates.filter((c) => selected[c.id]));
	const newCount = $derived(chosen.filter((c) => c.imported_device_id == null).length);

	async function importSelected() {
		busy = true;
		try {
			const res = await api.post<{ imported: number[] }>('/mqtt/import', {
				devices: chosen.map((c) => ({ id: c.id }))
			});
			importedCount = res.imported.length;
			clearTimeout(pollTimer);
			await home.refresh();
		} catch (e) {
			toast(errorMessage(e), 'error');
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head><title>Conectar aparelhos MQTT · Cordyhome</title></svelte:head>

<a class="back" href={to('/adicionar')}><ChevronLeft size={18} /> Adicionar aparelhos</a>

<div class="wizard">
	{#if importedCount != null}
		<section class="card panel center">
			<span class="done-icon"><Check size={26} strokeWidth={2.4} /></span>
			<h1>Pronto</h1>
			<p class="muted">{importedCount} {importedCount === 1 ? 'aparelho conectado' : 'aparelhos conectados'}. O estado chega na hora, sempre que o aparelho muda.</p>
			<div class="row">
				<button class="btn" type="button" onclick={() => { importedCount = null; refresh(); }}>Adicionar mais</button>
				<button class="btn primary" type="button" onclick={() => goto(to('/'))}>Ir para o início</button>
			</div>
		</section>
	{:else if !status}
		<section class="card panel center"><LoaderCircle size={28} class="spin" /></section>
	{:else if !status.enabled}
		<section class="card panel">
			<h1>Conectar aparelhos por MQTT</h1>
			<p class="muted lead">
				Muitos aparelhos falam MQTT direto na rede de casa, sem nuvem: os SONOFF com OpenEdge (MINI ONE PM, MINI PM),
				e qualquer aparelho com Tasmota, ESPHome ou Shelly. Eles se conectam a um servidor MQTT e se apresentam sozinhos.
			</p>
			<form class="setup" onsubmit={enable}>
				<fieldset class="modes">
					<legend class="eyebrow">Servidor MQTT</legend>
					<label class="mode" class:active={mode === 'embedded'}>
						<input type="radio" bind:group={mode} value="embedded" />
						<span>
							<strong>Usar o servidor do Cordyhome</strong>
							<span class="muted small">Recomendado. O Cordyhome cria o servidor, o usuário e a senha.</span>
						</span>
					</label>
					<label class="mode" class:active={mode === 'external'}>
						<input type="radio" bind:group={mode} value="external" />
						<span>
							<strong>Já tenho um servidor</strong>
							<span class="muted small">Mosquitto, o do Home Assistant ou outro que já roda na casa.</span>
						</span>
					</label>
				</fieldset>

				{#if mode === 'external'}
					<div class="grid">
						<label class="field">
							<span>Endereço</span>
							<input class="input mono" bind:value={host} placeholder="192.168.50.10" autocomplete="off" spellcheck="false" required />
						</label>
						<label class="field">
							<span>Porta</span>
							<input class="input mono" type="number" min="1" max="65535" bind:value={port} required />
						</label>
						<label class="field">
							<span>Usuário</span>
							<input class="input" bind:value={username} autocomplete="off" autocapitalize="none" />
						</label>
						<label class="field">
							<span>Senha</span>
							<input class="input" type="password" bind:value={password} autocomplete="new-password" />
						</label>
					</div>
				{/if}

				{#if error}<p class="error" role="alert">{error}</p>{/if}
				<div>
					<button class="btn primary" type="submit" disabled={busy}>
						{#if busy}<LoaderCircle size={16} class="spin" />{/if} Ativar MQTT
					</button>
				</div>
			</form>
		</section>
	{:else}
		<section class="card panel">
			<div class="head">
				<h1>MQTT</h1>
				{#if status.connected}
					<span class="pill accent"><Check size={12} /> Funcionando</span>
				{:else if status.error}
					<span class="pill critical">Sem conexão</span>
				{:else}
					<span class="pill"><LoaderCircle size={12} class="spin" /> Conectando</span>
				{/if}
			</div>
			{#if status.error}<p class="error" role="alert">{status.error}</p>{/if}

			{#if status.mode === 'embedded'}
				<p class="muted">Digite estes dados nas configurações de MQTT de cada aparelho:</p>
				<dl class="creds">
					<div>
						<dt><Server size={14} /> Servidor</dt>
						<dd>
							{#each status.addresses as address (address)}
								<button class="copy mono" type="button" onclick={() => copy(address)} title="Copiar">{address} <Copy size={13} /></button>
							{:else}
								<span class="faint">O IP deste computador</span>
							{/each}
						</dd>
					</div>
					<div>
						<dt><Plug size={14} /> Porta</dt>
						<dd><button class="copy mono" type="button" onclick={() => copy(String(status!.port))}>{status.port} <Copy size={13} /></button></dd>
					</div>
					<div>
						<dt>Usuário</dt>
						<dd><button class="copy mono" type="button" onclick={() => copy(status!.username)}>{status.username} <Copy size={13} /></button></dd>
					</div>
					<div>
						<dt><KeyRound size={14} /> Senha</dt>
						<dd>
							<button class="copy mono" type="button" onclick={() => copy(status!.password ?? '')}>{status.password} <Copy size={13} /></button>
						</dd>
					</div>
				</dl>
				{#if status.addresses.length > 1}
					<p class="faint small">Este computador tem mais de um endereço; use o da rede que o aparelho alcança.</p>
				{/if}

				<details class="how">
					<summary>Como fazer num SONOFF com OpenEdge</summary>
					<ol>
						<li>Abra no navegador o endereço do aparelho (o IP dele, ou algo como <span class="mono">MINI-1GSP.local</span>).</li>
						<li>Entre em <strong>MQTT</strong> e ative.</li>
						<li>Preencha servidor, porta, usuário e senha com os dados acima. Deixe sem TLS.</li>
						<li>Deixe ligada a descoberta do Home Assistant, com o prefixo <span class="mono">{status.discovery_prefix}</span>, e salve.</li>
					</ol>
					<p class="faint small">
						No Tasmota, ESPHome e Shelly o caminho é parecido: configure o servidor MQTT e ative a descoberta do Home Assistant.
						Se o aparelho fica numa rede separada (só para IoT), essa rede precisa alcançar este computador na porta {status.port}.
					</p>
				</details>
			{:else}
				<p class="muted">
					Usando o servidor <span class="mono">{status.host}:{status.port}</span>{status.username ? ` com o usuário ${status.username}` : ''}.
					Os aparelhos aparecem aqui quando anunciam a descoberta do Home Assistant (prefixo <span class="mono">{status.discovery_prefix}</span>).
				</p>
			{/if}
		</section>

		<section class="card panel">
			<div class="head">
				<div>
					<h2>Aparelhos encontrados</h2>
					<p class="muted small">A lista se atualiza sozinha conforme os aparelhos se conectam.</p>
				</div>
			</div>
			{#if candidates.length === 0}
				<p class="waiting muted"><LoaderCircle size={15} class="spin" /> Esperando o primeiro aparelho se conectar…</p>
			{:else}
				<ul class="candidates">
					{#each candidates as c (c.id)}
						<li>
							<label>
								<input type="checkbox" bind:checked={selected[c.id]} />
								<span class="icon"><KindIcon kind={c.kind} /></span>
								<span class="c-main">
									<span class="c-name">{c.name}</span>
									<span class="c-meta">
										{#if c.product_name}<span class="faint small">{c.product_name}</span>{/if}
										{#if c.has_energy_meter}<span class="pill accent"><Gauge size={12} /> Mede energia</span>{/if}
										{#if !c.capabilities.includes('power')}<span class="pill">Só medição</span>{/if}
										{#if c.imported_device_id != null}<span class="pill">Já adicionado · atualizar</span>{/if}
									</span>
								</span>
							</label>
						</li>
					{/each}
				</ul>
			{/if}
		</section>

		<div class="secondary">
			{#if status.mode === 'embedded'}
				<button class="btn sm ghost" type="button" onclick={newPassword}>Gerar nova senha</button>
			{/if}
			<button class="btn sm ghost danger" type="button" onclick={disable}>Desativar MQTT</button>
		</div>
		<div class="footer">
			<button class="btn primary big" type="button" disabled={busy || chosen.length === 0} onclick={importSelected}>
				{#if busy}<LoaderCircle size={16} class="spin" />{/if}
				{newCount > 0 ? `Adicionar ${newCount} ${newCount === 1 ? 'aparelho' : 'aparelhos'}` : chosen.length ? 'Atualizar selecionados' : 'Selecione aparelhos'}
			</button>
		</div>
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
	.panel {
		padding: 24px;
		display: grid;
		gap: 16px;
	}
	.lead {
		max-width: 560px;
	}
	.small {
		font-size: 13px;
	}
	.mono {
		font-family: var(--mono);
	}
	.error {
		color: var(--critical);
		font-size: 14px;
	}
	.head {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 12px;
	}
	.setup {
		display: grid;
		gap: 16px;
	}
	.modes {
		border: 0;
		margin: 0;
		padding: 0;
		display: grid;
		gap: 10px;
	}
	.modes legend {
		margin-bottom: 8px;
	}
	.mode {
		display: flex;
		gap: 12px;
		align-items: flex-start;
		padding: 14px 16px;
		border: 1px solid var(--border);
		border-radius: var(--radius);
		cursor: pointer;
	}
	.mode.active {
		border-color: var(--accent);
		background: var(--accent-soft);
	}
	.mode input {
		margin-top: 3px;
		accent-color: var(--accent-mark);
	}
	.mode > span {
		display: grid;
		gap: 2px;
	}
	.grid {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 12px;
	}
	@media (max-width: 560px) {
		.grid {
			grid-template-columns: 1fr;
		}
	}
	.creds {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
		gap: 12px;
		margin: 0;
	}
	.creds div {
		padding: 12px 14px;
		border-radius: var(--radius);
		background: var(--surface-2);
		display: grid;
		gap: 6px;
		min-width: 0;
	}
	.creds dt {
		display: flex;
		align-items: center;
		gap: 6px;
		font-size: 12.5px;
		color: var(--text-2);
		font-weight: 550;
	}
	.creds dd {
		margin: 0;
		display: grid;
		gap: 4px;
	}
	.copy {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		padding: 0;
		border: 0;
		background: none;
		color: var(--text);
		font-size: 15px;
		font-weight: 600;
		cursor: pointer;
		text-align: left;
		overflow-wrap: anywhere;
	}
	.copy :global(svg) {
		flex: none;
		color: var(--text-3);
	}
	.how {
		padding: 14px 16px;
		border-radius: var(--radius);
		background: var(--surface-2);
		font-size: 14px;
	}
	.how summary {
		font-weight: 600;
		cursor: pointer;
	}
	.how ol {
		margin: 10px 0;
		padding-left: 20px;
		display: grid;
		gap: 6px;
	}
	.waiting {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 14px;
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
	.icon {
		display: grid;
		place-items: center;
		width: 34px;
		height: 34px;
		flex: none;
		border-radius: 10px;
		background: var(--surface-2);
		color: var(--text-2);
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
	.secondary {
		display: flex;
		flex-wrap: wrap;
		gap: 4px;
		margin-top: -8px;
	}
	.footer {
		position: sticky;
		bottom: calc(var(--tabbar) + 12px + env(safe-area-inset-bottom));
		display: flex;
		justify-content: flex-end;
	}
	@media (min-width: 900px) {
		.footer {
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
	.center {
		justify-items: center;
		text-align: center;
		padding: 48px 24px;
	}
	.row {
		display: flex;
		gap: 8px;
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
