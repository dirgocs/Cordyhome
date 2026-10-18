import { api } from './api';
import { errorMessage, home, toast } from './state.svelte';
import type { Device, DeviceState } from './types';

/** Dispositivos com comando em andamento (mostram o estado otimista com indicador). */
export const pending = $state<Record<number, boolean>>({});

export const confirmation = $state<{
	device: Device | null;
	resolve: ((ok: boolean) => void) | null;
}>({ device: null, resolve: null });

function askConfirm(device: Device): Promise<boolean> {
	return new Promise((resolve) => {
		confirmation.device = device;
		confirmation.resolve = resolve;
	});
}

export function answerConfirm(ok: boolean) {
	confirmation.resolve?.(ok);
	confirmation.device = null;
	confirmation.resolve = null;
}

export async function setPower(device: Device, on: boolean) {
	if (pending[device.id]) return;
	if (!on && device.confirm_off && !(await askConfirm(device))) return;
	pending[device.id] = true;
	home.upsert({ ...device, is_on: on });
	try {
		home.upsert(await api.post<Device>(`/devices/${device.id}/power`, { on }));
	} catch (error) {
		home.upsert(device);
		toast(errorMessage(error), 'error');
	} finally {
		delete pending[device.id];
	}
}

/** Brilho, temperatura de cor ou cor. Mostra o novo estado na hora e confirma com o hub. */
export async function setState(device: Device, changes: DeviceState) {
	home.upsert({ ...device, is_on: true, state: { ...device.state, ...changes } });
	try {
		home.upsert(await api.post<Device>(`/devices/${device.id}/state`, changes));
	} catch (error) {
		home.upsert(device);
		toast(errorMessage(error), 'error');
	}
}
