import { api, ApiError } from './api';
import type { Device, Room } from './types';

type Topic = 'devices' | 'rooms' | 'alerts' | 'schedules' | 'energy' | 'settings';

/** Sessão do usuário logado. */
export const session = $state<{
	ready: boolean;
	setupRequired: boolean;
	user: { id: number; username: string } | null;
}>({ ready: false, setupRequired: false, user: null });

export async function loadSession() {
	const status = await api.get<{
		setup_required: boolean;
		user: { id: number; username: string } | null;
	}>('/auth/status');
	session.setupRequired = status.setup_required;
	session.user = status.user;
	session.ready = true;
}

/**
 * Estado compartilhado da casa: dispositivos e cômodos, mantidos em dia pelo WebSocket.
 * As páginas leem daqui para que um liga/desliga reflita em todas as telas ao mesmo tempo.
 */
class HomeState {
	devices = $state<Device[]>([]);
	rooms = $state<Room[]>([]);
	loaded = $state(false);
	unreadAlerts = $state(0);
	connected = $state(true);
	/** Contadores que mudam quando um tópico é atualizado no hub; páginas reagem a eles. */
	versions = $state<Record<Topic, number>>({
		devices: 0,
		rooms: 0,
		alerts: 0,
		schedules: 0,
		energy: 0,
		settings: 0
	});

	#ws: WebSocket | null = null;
	#retry = 0;
	#stopped = false;

	byId(id: number): Device | undefined {
		return this.devices.find((d) => d.id === id);
	}

	roomName(id: number | null): string {
		return this.rooms.find((r) => r.id === id)?.name ?? 'Sem cômodo';
	}

	upsert(device: Device) {
		const index = this.devices.findIndex((d) => d.id === device.id);
		if (index >= 0) this.devices[index] = device;
		else this.devices.push(device);
	}

	async refresh() {
		const [devices, rooms, alerts] = await Promise.all([
			api.get<Device[]>('/devices'),
			api.get<Room[]>('/rooms'),
			api.get<{ unread: number }>('/alerts?filter=unread&limit=1')
		]);
		this.devices = devices;
		this.rooms = rooms;
		this.unreadAlerts = alerts.unread;
		this.loaded = true;
	}

	connect() {
		this.#stopped = false;
		if (this.#ws) return;
		const proto = location.protocol === 'https:' ? 'wss' : 'ws';
		const ws = new WebSocket(`${proto}://${location.host}/api/ws`);
		this.#ws = ws;
		ws.onopen = () => {
			const reconnected = this.#retry > 0;
			this.#retry = 0;
			this.connected = true;
			// Depois de uma queda, o estado pode estar velho.
			if (reconnected) this.refresh().catch(() => {});
		};
		ws.onmessage = (event) => this.#handle(JSON.parse(event.data));
		ws.onclose = () => {
			this.#ws = null;
			if (this.#stopped) return;
			this.connected = false;
			const delay = Math.min(15000, 1000 * 2 ** this.#retry++);
			setTimeout(() => this.connect(), delay);
		};
	}

	disconnect() {
		this.#stopped = true;
		this.#ws?.close();
		this.#ws = null;
	}

	#handle(message: { type: string; device?: Device }) {
		switch (message.type) {
			case 'device':
				if (message.device) this.upsert(message.device);
				this.versions.devices++;
				break;
			case 'devices':
				this.refresh().catch(() => {});
				this.versions.devices++;
				break;
			case 'rooms':
				api.get<Room[]>('/rooms').then((rooms) => (this.rooms = rooms));
				this.versions.rooms++;
				break;
			case 'alerts':
				api
					.get<{ unread: number }>('/alerts?filter=unread&limit=1')
					.then((a) => (this.unreadAlerts = a.unread));
				this.versions.alerts++;
				break;
			case 'schedules':
			case 'energy':
			case 'settings':
				this.versions[message.type]++;
				break;
		}
	}
}

export const home = new HomeState();

/* ----------------------------------------------------------------------------- avisos */

export interface Toast {
	id: number;
	message: string;
	tone: 'default' | 'error';
}

export const toasts = $state<Toast[]>([]);
let toastId = 0;

export function toast(message: string, tone: Toast['tone'] = 'default') {
	if (!message) return;
	const id = ++toastId;
	toasts.push({ id, message, tone });
	setTimeout(() => {
		const index = toasts.findIndex((t) => t.id === id);
		if (index >= 0) toasts.splice(index, 1);
	}, 4200);
}

export function errorMessage(error: unknown): string {
	// Sessão expirada já redireciona para o login; não vale um aviso.
	if (error instanceof ApiError && error.status === 401) return '';
	return error instanceof Error ? error.message : 'Algo deu errado.';
}
