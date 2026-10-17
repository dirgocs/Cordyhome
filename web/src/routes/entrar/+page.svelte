<script lang="ts">
	import { to } from '$lib/nav';
	import { goto } from '$app/navigation';
	import { api } from '$lib/api';
	import Logo from '$lib/components/Logo.svelte';
	import { errorMessage, session } from '$lib/state.svelte';

	let username = $state('');
	let password = $state('');
	let error = $state('');
	let busy = $state(false);
	const setup = $derived(session.setupRequired);

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		error = '';
		busy = true;
		try {
			const res = await api.post<{ user: { id: number; username: string } }>(
				setup ? '/auth/setup' : '/auth/login',
				{ username, password }
			);
			session.user = res.user;
			session.setupRequired = false;
			await goto(to('/'), { replaceState: true });
		} catch (e) {
			// Aqui o 401 é "senha errada", não sessão expirada: mostra a mensagem do hub.
			error = e instanceof Error ? e.message : errorMessage(e);
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head><title>{setup ? 'Bem-vindo' : 'Entrar'} · Cordyhome</title></svelte:head>

<div class="auth">
	<form class="card" onsubmit={submit}>
		<div class="brand"><Logo size={30} /> Cordyhome</div>
		<div>
			<h1>{setup ? 'Crie sua conta' : 'Entrar'}</h1>
			<p class="muted">
				{setup
					? 'Primeiro acesso. Essa conta protege o controle da sua casa, inclusive quando você acessar de fora.'
					: 'Acesse o painel da sua casa.'}
			</p>
		</div>
		<label class="field">
			<span>Usuário</span>
			<input class="input" bind:value={username} autocomplete="username" required autocapitalize="none" />
		</label>
		<label class="field">
			<span>Senha</span>
			<input
				class="input"
				type="password"
				bind:value={password}
				autocomplete={setup ? 'new-password' : 'current-password'}
				minlength={setup ? 8 : undefined}
				required
			/>
			{#if setup}<small>Pelo menos 8 caracteres.</small>{/if}
		</label>
		{#if error}<p class="error" role="alert">{error}</p>{/if}
		<button class="btn primary" type="submit" disabled={busy}>
			{busy ? 'Aguarde…' : setup ? 'Criar conta e continuar' : 'Entrar'}
		</button>
	</form>
</div>

<style>
	.auth {
		min-height: 100dvh;
		display: grid;
		place-items: center;
		padding: 24px 16px;
	}
	form {
		width: min(400px, 100%);
		display: grid;
		gap: 18px;
		padding: 28px 24px;
	}
	.brand {
		display: flex;
		align-items: center;
		gap: 10px;
		font-weight: 650;
		font-size: 17px;
		letter-spacing: -0.02em;
		margin-bottom: 8px;
	}
	h1 {
		font-size: 22px;
		margin-bottom: 6px;
	}
	.btn {
		height: 44px;
		margin-top: 4px;
	}
	.error {
		color: var(--critical);
		font-size: 14px;
	}
</style>
