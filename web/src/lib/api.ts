import { to } from './nav';
import { goto } from '$app/navigation';

export class ApiError extends Error {
	constructor(
		public status: number,
		message: string
	) {
		super(message);
	}
}

function detailMessage(body: unknown, status: number): string {
	if (body && typeof body === 'object' && 'detail' in body) {
		const detail = (body as { detail: unknown }).detail;
		if (typeof detail === 'string') return detail;
		if (Array.isArray(detail) && detail[0]?.msg) {
			return String(detail[0].msg).replace(/^Value error, /, '');
		}
	}
	if (status >= 500) return 'O hub não respondeu como esperado. Tente de novo.';
	return 'Algo deu errado.';
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
	if (import.meta.env.VITE_PROTOTYPE === '1') {
		// Protótipo: responde com o hub simulado no navegador.
		const { mockRequest } = await import('./mock/server');
		const { status, data } = await mockRequest(method, path, body);
		if (status >= 400) {
			if (status === 401 && !path.startsWith('/auth/')) await goto(to('/entrar'));
			throw new ApiError(status, detailMessage(data, status));
		}
		return data as T;
	}
	let res: Response;
	try {
		res = await fetch(`/api${path}`, {
			method,
			credentials: 'same-origin',
			headers: body === undefined ? undefined : { 'content-type': 'application/json' },
			body: body === undefined ? undefined : JSON.stringify(body)
		});
	} catch {
		throw new ApiError(0, 'Sem conexão com o hub. Ele está ligado?');
	}
	if (res.status === 204) return undefined as T;
	const data = await res.json().catch(() => null);
	if (!res.ok) {
		if (res.status === 401 && !path.startsWith('/auth/')) {
			await goto(to('/entrar'));
		}
		throw new ApiError(res.status, detailMessage(data, res.status));
	}
	return data as T;
}

export const api = {
	get: <T>(path: string) => request<T>('GET', path),
	post: <T>(path: string, body: unknown = {}) => request<T>('POST', path, body),
	patch: <T>(path: string, body: unknown) => request<T>('PATCH', path, body),
	put: <T>(path: string, body: unknown) => request<T>('PUT', path, body),
	del: <T = void>(path: string) => request<T>('DELETE', path)
};
