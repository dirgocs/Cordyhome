/**
 * Hub simulado para o protótipo publicado como artefato: responde às mesmas rotas da API real,
 * com uma casa de demonstração (tomadas Steck/Tuya), histórico de 60 dias e consumo ao vivo.
 * Só é carregado quando VITE_PROTOTYPE=1; o app real nunca inclui este arquivo.
 */
import type {
	Alert,
	Device,
	DeviceKind,
	EnergyReport,
	RangeKey,
	Room,
	Schedule,
	Settings,
	TuyaCandidate
} from '../types';

type Listener = (message: { type: string; device?: Device }) => void;

class MockError extends Error {
	constructor(
		public status: number,
		message: string
	) {
		super(message);
	}
}

// ------------------------------------------------------------------ utilidades

function rng(seed: number) {
	return () => {
		seed = (seed * 1664525 + 1013904223) % 4294967296;
		return seed / 4294967296;
	};
}
const random = rng(7);
const HOUR = 3600;
const now = () => Date.now() / 1000;
const hourStart = (ts: number) => Math.floor(ts / HOUR) * HOUR;
const delay = () => new Promise((r) => setTimeout(r, 120 + Math.random() * 180));

// ------------------------------------------------------------------ casa de demonstração

interface Profile {
	name: string;
	room: string;
	kind: DeviceKind;
	watts: number;
	hours: number[];
	protect?: boolean;
	alert?: number;
	offline?: boolean;
}

const ROOMS = ['Sala', 'Cozinha', 'Quarto', 'Escritório', 'Área de serviço', 'Varanda'];
const range = (a: number, b: number) => Array.from({ length: b - a }, (_, i) => a + i);

const PROFILES: Profile[] = [
	{ name: 'TV', room: 'Sala', kind: 'plug', watts: 95, hours: range(19, 24) },
	{ name: 'Luminária de chão', room: 'Sala', kind: 'light', watts: 12, hours: range(18, 24) },
	{ name: 'Geladeira', room: 'Cozinha', kind: 'plug', watts: 140, hours: range(0, 24), protect: true },
	{ name: 'Cafeteira', room: 'Cozinha', kind: 'plug', watts: 800, hours: [7], alert: 1500 },
	{ name: 'Micro-ondas', room: 'Cozinha', kind: 'plug', watts: 1100, hours: [12, 20], alert: 1500 },
	{ name: 'Ar-condicionado', room: 'Quarto', kind: 'plug', watts: 850, hours: [0, 1, 2, 3, 4, 5, 22, 23], alert: 1500 },
	{ name: 'Carregador do celular', room: 'Quarto', kind: 'plug', watts: 8, hours: range(0, 6) },
	{ name: 'Computador', room: 'Escritório', kind: 'plug', watts: 180, hours: range(9, 18) },
	{ name: 'Monitor', room: 'Escritório', kind: 'plug', watts: 28, hours: range(9, 18) },
	{ name: 'Máquina de lavar', room: 'Área de serviço', kind: 'plug', watts: 450, hours: [10] },
	{ name: 'Luminária da varanda', room: 'Varanda', kind: 'light', watts: 9, hours: range(18, 23), offline: true }
];

// Tomadas que existem na conta Tuya além das já importadas (para o assistente).
const EXTRA_TUYA = [
	['Ventilador', 'Quarto'],
	['Umidificador', 'Quarto'],
	['Roteador', 'Escritório'],
	['Impressora', 'Escritório'],
	['Air fryer', 'Cozinha'],
	['Freezer', 'Área de serviço'],
	['Aquecedor', 'Sala']
] as const;

interface Sim {
	profile: Profile;
	device: Device;
	hourly: Map<number, number>; // início da hora -> Wh
	minutes: { ts: number; w: number }[];
	lastSample: number;
}

const state = {
	user: { id: 1, username: 'diego' } as { id: number; username: string } | null,
	rooms: [] as Room[],
	sims: [] as Sim[],
	schedules: [] as Schedule[],
	alerts: [] as Alert[],
	settings: {
		tariff_per_kwh: 0.85,
		timezone: 'America/Sao_Paulo',
		poll_interval_sec: 10,
		offline_after_failures: 3
	} as Settings,
	tuya: { linked: true, username: 'diego@exemplo.com', linked_at: now() - 86400 * 20 },
	pendingLogin: null as { token: string; started: number } | null,
	nextId: 100
};

const listeners = new Set<Listener>();
function emit(type: string, device?: Device) {
	for (const l of listeners) l({ type, device });
}
export function subscribe(listener: Listener) {
	listeners.add(listener);
	return () => listeners.delete(listener);
}

function makeDevice(id: number, p: Profile, roomId: number | null, on: boolean): Device {
	return {
		id,
		name: p.name,
		room_id: roomId,
		kind: p.kind,
		adapter: 'tuya',
		enabled: true,
		sort_order: id,
		online: !p.offline,
		is_on: p.offline ? true : on,
		power_w: null,
		power_estimated: false,
		voltage_v: 127,
		current_a: 0,
		last_seen: p.offline ? now() - 3 * HOUR : now(),
		last_error: p.offline ? 'Sem resposta na rede. Verifique se a tomada está energizada e no Wi-Fi.' : null,
		nominal_watts: null,
		power_alert_watts: p.alert ?? null,
		confirm_off: !!p.protect,
		info: {
			ip: `192.168.0.${110 + id}`,
			protocol_version: 3.4,
			product_name: 'Tomada Inteligente Steck 10A',
			has_energy_meter: true
		}
	};
}

function usage(p: Profile, ts: number, r: () => number): number {
	const h = new Date(ts * 1000).getHours();
	if (p.name === 'Geladeira') return p.watts * (0.45 + 0.1 * Math.sin((h / 24) * Math.PI * 2));
	const on = p.hours.includes(h) && r() > 0.15;
	return on ? p.watts * (0.35 + r() * 0.65) : p.watts > 50 ? 0.5 : 0.2;
}

function livePower(sim: Sim): number {
	const { device, profile } = sim;
	if (!device.online) return 0;
	if (!device.is_on) return profile.watts > 50 ? 0.5 : 0.2;
	const wave = 1 + 0.08 * Math.sin(now() / 60 + device.id);
	const base = profile.name === 'Geladeira' ? profile.watts * (random() > 0.4 ? 1 : 0.05) : profile.watts;
	return Math.max(0, base * wave * (0.97 + random() * 0.06));
}

function seed() {
	state.rooms = ROOMS.map((name, i) => ({ id: i + 1, name, sort_order: i }));
	const r = rng(42);
	const t = now();
	const currentHour = new Date().getHours();
	state.sims = PROFILES.map((p, i) => {
		const id = i + 1;
		const roomId = state.rooms.find((room) => room.name === p.room)!.id;
		const on = p.hours.includes(currentHour) || !!p.protect;
		const device = makeDevice(id, p, roomId, on);
		const hourly = new Map<number, number>();
		for (let ts = hourStart(t - 60 * 86400); ts < hourStart(t); ts += HOUR) {
			if (p.offline && ts > t - 3 * HOUR) continue;
			hourly.set(ts, usage(p, ts, r));
		}
		const minutes: { ts: number; w: number }[] = [];
		for (let ts = Math.floor((t - 86400) / 60) * 60; ts < t; ts += 60) {
			if (p.offline && ts > t - 3 * HOUR) continue;
			minutes.push({ ts, w: usage(p, ts, r) });
		}
		const sim: Sim = { profile: p, device, hourly, minutes, lastSample: t };
		device.power_w = livePower(sim);
		device.current_a = device.power_w / 127;
		return sim;
	});

	const days = { all: 0b1111111, work: 0b0111110 };
	const find = (name: string) => state.sims.find((s) => s.device.name === name)!.device;
	const sched = (device: Device, action: Schedule['action'], time: string, d: number): Schedule => ({
		id: state.nextId++,
		device_id: device.id,
		device_name: device.name,
		room_id: device.room_id,
		action,
		time,
		days: d,
		enabled: true,
		next_run: null,
		last_run_at: null,
		last_result: null
	});
	state.schedules = [
		sched(find('Cafeteira'), 'on', '06:50', days.work),
		sched(find('Cafeteira'), 'off', '07:30', days.work),
		sched(find('Ar-condicionado'), 'off', '06:00', days.all),
		{ ...sched(find('Luminária de chão'), 'on', '18:30', days.all), enabled: false }
	];

	const varanda = find('Luminária da varanda');
	const micro = find('Micro-ondas');
	state.alerts = [
		{
			id: state.nextId++,
			device_id: varanda.id,
			device_name: varanda.name,
			kind: 'offline',
			severity: 'warning',
			message: `${varanda.name} está sem comunicação. ${varanda.last_error}`,
			created_at: t - 3 * HOUR,
			resolved_at: null,
			acknowledged: false
		},
		{
			id: state.nextId++,
			device_id: micro.id,
			device_name: micro.name,
			kind: 'high_power',
			severity: 'critical',
			message: `${micro.name} está consumindo 1640 W (limite 1500 W).`,
			created_at: t - 26 * HOUR,
			resolved_at: t - 26 * HOUR + 180,
			acknowledged: true
		}
	];
}
seed();

// Leitura periódica simulada: potência oscila e a energia acumula na hora corrente.
setInterval(() => {
	const t = now();
	for (const sim of state.sims) {
		const { device } = sim;
		if (!device.online) continue;
		const prev = device.power_w ?? 0;
		const power = livePower(sim);
		const wh = ((prev + power) / 2) * ((t - sim.lastSample) / 3600);
		sim.hourly.set(hourStart(t), (sim.hourly.get(hourStart(t)) ?? 0) + wh);
		const minute = Math.floor(t / 60) * 60;
		const last = sim.minutes[sim.minutes.length - 1];
		if (last?.ts === minute) last.w = (last.w + power) / 2;
		else sim.minutes.push({ ts: minute, w: power });
		sim.lastSample = t;
		device.power_w = Math.round(power * 10) / 10;
		device.voltage_v = 125 + Math.random() * 4;
		device.current_a = power / device.voltage_v;
		device.last_seen = t;
		emit('device', { ...device, info: { ...device.info } });
	}
}, 5000);
setInterval(() => emit('energy'), 60_000);

// ------------------------------------------------------------------ energia

function periodFor(key: RangeKey): { start: Date; end: Date; bucket: 'hour' | 'day' | 'month' } {
	const today = new Date();
	today.setHours(0, 0, 0, 0);
	const addDays = (d: Date, n: number) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
	const month = (d: Date, n: number) => new Date(d.getFullYear(), d.getMonth() + n, 1);
	switch (key) {
		case 'today':
			return { start: today, end: addDays(today, 1), bucket: 'hour' };
		case 'yesterday':
			return { start: addDays(today, -1), end: today, bucket: 'hour' };
		case '7d':
			return { start: addDays(today, -6), end: addDays(today, 1), bucket: 'day' };
		case '30d':
			return { start: addDays(today, -29), end: addDays(today, 1), bucket: 'day' };
		case 'month':
			return { start: month(today, 0), end: month(today, 1), bucket: 'day' };
		case '12m':
			return { start: month(today, -11), end: month(today, 1), bucket: 'month' };
	}
}

function bucketStarts(start: Date, end: Date, bucket: 'hour' | 'day' | 'month'): Date[] {
	const out: Date[] = [];
	let c = new Date(start);
	while (c < end) {
		out.push(c);
		if (bucket === 'hour') c = new Date(c.getTime() + HOUR * 1000);
		else if (bucket === 'day') c = new Date(c.getFullYear(), c.getMonth(), c.getDate() + 1);
		else c = new Date(c.getFullYear(), c.getMonth() + 1, 1);
	}
	return out;
}

function bucketKey(ts: number, bucket: 'hour' | 'day' | 'month'): number {
	const d = new Date(ts * 1000);
	if (bucket === 'hour') d.setMinutes(0, 0, 0);
	else if (bucket === 'day') d.setHours(0, 0, 0, 0);
	else return new Date(d.getFullYear(), d.getMonth(), 1).getTime();
	return d.getTime();
}

function report(key: RangeKey, deviceIds?: number[]): EnergyReport {
	const { start, end, bucket } = periodFor(key);
	const s = start.getTime() / 1000;
	const e = end.getTime() / 1000;
	const series = new Map(bucketStarts(start, end, bucket).map((d) => [d.getTime(), 0]));
	const perDevice = new Map<number, number>();
	for (const sim of state.sims) {
		if (deviceIds && !deviceIds.includes(sim.device.id)) continue;
		for (const [ts, wh] of sim.hourly) {
			if (ts < s || ts >= e) continue;
			const k = bucketKey(ts, bucket);
			if (series.has(k)) series.set(k, series.get(k)! + wh);
			perDevice.set(sim.device.id, (perDevice.get(sim.device.id) ?? 0) + wh);
		}
	}
	const tariff = state.settings.tariff_per_kwh;
	const totalWh = [...perDevice.values()].reduce((a, b) => a + b, 0);
	const elapsed = Math.max(0, Math.min(now(), e) - s);
	const projected = key === 'month' && elapsed > 6 * HOUR ? ((totalWh / elapsed) * (e - s)) / 1000 : null;
	const devices = [...perDevice.entries()]
		.sort((a, b) => b[1] - a[1])
		.map(([id, wh]) => {
			const d = state.sims.find((x) => x.device.id === id)!.device;
			return { device_id: id, name: d.name, room_id: d.room_id, kwh: wh / 1000, cost: (wh / 1000) * tariff };
		});
	const rooms = new Map<number | null, number>();
	for (const d of devices) rooms.set(d.room_id, (rooms.get(d.room_id) ?? 0) + d.kwh);
	return {
		range: key,
		bucket,
		start: start.toISOString(),
		end: end.toISOString(),
		total_kwh: totalWh / 1000,
		cost: (totalWh / 1000) * tariff,
		projected_kwh: projected,
		projected_cost: projected == null ? null : projected * tariff,
		series: [...series.entries()].map(([ms, wh]) => ({ start: new Date(ms).toISOString(), kwh: wh / 1000 })),
		devices,
		rooms: [...rooms.entries()]
			.sort((a, b) => b[1] - a[1])
			.map(([room_id, kwh]) => ({ room_id, kwh, cost: kwh * tariff })),
		tariff_per_kwh: tariff
	};
}

function downsample(points: { ts: number; w: number }[], step: number) {
	const buckets = new Map<number, number[]>();
	for (const p of points) {
		const k = Math.floor(p.ts / step) * step;
		buckets.set(k, [...(buckets.get(k) ?? []), p.w]);
	}
	return [...buckets.entries()].sort((a, b) => a[0] - b[0]).map(([ts, v]) => ({ ts, w: v.reduce((a, b) => a + b, 0) / v.length }));
}

// ------------------------------------------------------------------ rotinas

function nextRun(s: Schedule): string | null {
	if (!s.enabled) return null;
	const [h, m] = s.time.split(':').map(Number);
	const base = new Date();
	for (let i = 0; i < 8; i++) {
		const c = new Date(base.getFullYear(), base.getMonth(), base.getDate() + i, h, m);
		if (c > base && s.days & (1 << c.getDay())) return c.toISOString();
	}
	return null;
}

function schedules(): Schedule[] {
	return state.schedules
		.map((s) => {
			const d = state.sims.find((x) => x.device.id === s.device_id)?.device;
			return { ...s, device_name: d?.name ?? s.device_name, room_id: d?.room_id ?? null, next_run: nextRun(s) };
		})
		.sort((a, b) => (a.next_run ?? '~').localeCompare(b.next_run ?? '~'));
}

let lastScheduleMinute = '';
setInterval(() => {
	const d = new Date();
	const key = `${d.toDateString()} ${d.getHours()}:${d.getMinutes()}`;
	if (key === lastScheduleMinute) return;
	lastScheduleMinute = key;
	const hhmm = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
	for (const s of state.schedules) {
		if (!s.enabled || s.time !== hhmm || !(s.days & (1 << d.getDay()))) continue;
		const sim = state.sims.find((x) => x.device.id === s.device_id);
		if (!sim) continue;
		const on = s.action === 'toggle' ? !sim.device.is_on : s.action === 'on';
		setPower(sim, on);
		s.last_run_at = now();
		s.last_result = 'ok';
		emit('schedules');
	}
}, 10_000);

// ------------------------------------------------------------------ comandos

function sim(id: number): Sim {
	const found = state.sims.find((s) => s.device.id === id);
	if (!found) throw new MockError(404, 'Dispositivo não encontrado.');
	return found;
}

function setPower(target: Sim, on: boolean): Device {
	if (!target.device.online) {
		throw new MockError(502, 'Sem resposta na rede. Verifique se a tomada está energizada e no Wi-Fi.');
	}
	target.device.is_on = on;
	target.device.power_w = Math.round(livePower(target) * 10) / 10;
	const copy = { ...target.device, info: { ...target.device.info } };
	emit('device', copy);
	return copy;
}

function deviceDetail(id: number) {
	const s = sim(id);
	const today = report('today', [id]);
	const month = report('month', [id]);
	return {
		...s.device,
		energy: {
			today_kwh: today.total_kwh,
			today_cost: today.cost,
			month_kwh: month.total_kwh,
			month_cost: month.cost,
			projected_cost: month.projected_cost,
			daily: report('30d', [id]).series
		},
		power_history: downsample(s.minutes, 300).map((p) => ({ ts: p.ts, avg_w: p.w })),
		schedules: schedules().filter((x) => x.device_id === id),
		events: [
			{ ts: now() - 1800, source: 'user', action: s.device.is_on ? 'on' : 'off', detail: null },
			{ ts: now() - 6 * HOUR, source: 'schedule', action: 'off', detail: null },
			{ ts: now() - 20 * HOUR, source: 'device', action: 'on', detail: null }
		]
	};
}

// ------------------------------------------------------------------ Tuya

function fakeQr(): string {
	const n = 25;
	const r = rng(99);
	let cells = '';
	const finder = (x: number, y: number) =>
		`<rect x="${x}" y="${y}" width="7" height="7" fill="#111"/><rect x="${x + 1}" y="${y + 1}" width="5" height="5" fill="#fff"/><rect x="${x + 2}" y="${y + 2}" width="3" height="3" fill="#111"/>`;
	for (let y = 0; y < n; y++)
		for (let x = 0; x < n; x++) {
			const inFinder = (x < 8 && y < 8) || (x > n - 9 && y < 8) || (x < 8 && y > n - 9);
			if (!inFinder && r() > 0.52) cells += `<rect x="${x}" y="${y}" width="1" height="1" fill="#111"/>`;
		}
	return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="-2 -2 ${n + 4} ${n + 4}" shape-rendering="crispEdges"><rect x="-2" y="-2" width="${n + 4}" height="${n + 4}" fill="#fff"/>${cells}${finder(0, 0)}${finder(n - 7, 0)}${finder(0, n - 7)}</svg>`;
}

function candidates(): TuyaCandidate[] {
	const imported = state.sims.map((s) => ({
		id: `steck-${s.device.id}`,
		name: s.device.name,
		room: state.rooms.find((r) => r.id === s.device.room_id)?.name ?? null,
		kind: s.device.kind,
		product_name: s.device.info.product_name ?? 'Tomada Inteligente Steck 10A',
		cloud_online: s.device.online,
		local_supported: true,
		has_energy_meter: true,
		lan_ip: s.device.online ? s.device.info.ip : null,
		imported_device_id: s.device.id
	}));
	const extra = EXTRA_TUYA.filter(([name]) => !state.sims.some((s) => s.device.name === name)).map(
		([name, room], i) => ({
			id: `steck-new-${i}`,
			name,
			room,
			kind: 'plug' as DeviceKind,
			product_name: 'Tomada Inteligente Steck 10A',
			cloud_online: true,
			local_supported: true,
			has_energy_meter: true,
			lan_ip: i === 3 ? null : `192.168.0.${140 + i}`,
			imported_device_id: null
		})
	);
	return [...imported, ...extra];
}

function importDevices(items: { id: string; room?: string | null }[]): number[] {
	const ids: number[] = [];
	for (const item of items) {
		if (!item.id.startsWith('steck-new-')) {
			const existing = Number(item.id.replace('steck-', ''));
			if (state.sims.some((s) => s.device.id === existing)) ids.push(existing);
			continue;
		}
		const [name, roomName] = EXTRA_TUYA[Number(item.id.replace('steck-new-', ''))];
		let room = state.rooms.find((r) => r.name === (item.room ?? roomName));
		if (!room) {
			room = { id: state.nextId++, name: roomName, sort_order: state.rooms.length };
			state.rooms.push(room);
		}
		const profile: Profile = { name, room: room.name, kind: 'plug', watts: 40 + Math.round(random() * 400), hours: [] };
		const id = state.nextId++;
		const device = makeDevice(id, profile, room.id, false);
		state.sims.push({ profile, device, hourly: new Map(), minutes: [], lastSample: now() });
		ids.push(id);
	}
	emit('devices');
	return ids;
}

// ------------------------------------------------------------------ roteador

function publicDevices(): Device[] {
	return state.sims.map((s) => ({ ...s.device, info: { ...s.device.info } }));
}

function unreadAlerts() {
	return state.alerts.filter((a) => !a.acknowledged).length;
}

async function handle(method: string, path: string, body: any): Promise<unknown> {
	const [pathname, query = ''] = path.split('?');
	const q = new URLSearchParams(query);
	const parts = pathname.split('/').filter(Boolean);
	const route = `${method} /${parts.map((p) => (/^\d+$/.test(p) ? ':id' : p)).join('/')}`;
	const id = Number(parts.find((p) => /^\d+$/.test(p)));

	if (route.startsWith('GET /auth/status')) return { setup_required: false, user: state.user };
	if (route === 'POST /auth/login' || route === 'POST /auth/setup') {
		if (!body.password) throw new MockError(401, 'Usuário ou senha incorretos.');
		state.user = { id: 1, username: body.username || 'diego' };
		return { user: state.user };
	}
	if (route === 'POST /auth/logout') {
		state.user = null;
		return { ok: true };
	}
	if (!state.user) throw new MockError(401, 'Faça login para continuar.');

	switch (route) {
		case 'GET /home': {
			const devices = publicDevices();
			const today = report('today');
			const month = report('month');
			const total = state.sims.reduce<Map<number, number>>((acc, s) => {
				for (const m of s.minutes) if (m.ts > now() - 3 * HOUR) acc.set(m.ts, (acc.get(m.ts) ?? 0) + m.w);
				return acc;
			}, new Map());
			return {
				power_w: devices.reduce((a, d) => a + (d.online ? (d.power_w ?? 0) : 0), 0),
				power_history: downsample([...total.entries()].map(([ts, w]) => ({ ts, w })), 300),
				today: { kwh: today.total_kwh, cost: today.cost },
				month: { kwh: month.total_kwh, cost: month.cost, projected_cost: month.projected_cost },
				counts: {
					total: devices.length,
					online: devices.filter((d) => d.online).length,
					on: devices.filter((d) => d.online && d.is_on).length
				},
				unread_alerts: unreadAlerts(),
				next_schedules: schedules().slice(0, 3),
				rooms: state.rooms,
				devices,
				tariff_per_kwh: state.settings.tariff_per_kwh
			};
		}
		case 'GET /devices':
			return publicDevices();
		case 'GET /devices/:id':
			return deviceDetail(id);
		case 'PATCH /devices/:id': {
			const d = sim(id).device;
			if (body.name !== undefined && !String(body.name).trim()) throw new MockError(422, 'Informe um nome.');
			const { ip, protocol_version, ...rest } = body;
			Object.assign(d, rest);
			if (ip !== undefined) d.info.ip = ip || null;
			if (protocol_version !== undefined) d.info.protocol_version = protocol_version;
			emit('device', { ...d, info: { ...d.info } });
			return { ...d, info: { ...d.info } };
		}
		case 'DELETE /devices/:id':
			state.sims = state.sims.filter((s) => s.device.id !== id);
			state.schedules = state.schedules.filter((s) => s.device_id !== id);
			emit('devices');
			return undefined;
		case 'POST /devices/:id/power':
			return setPower(sim(id), !!body.on);
		case 'POST /devices/:id/toggle':
			return setPower(sim(id), !sim(id).device.is_on);
		case 'POST /devices/:id/refresh': {
			const s = sim(id);
			if (!s.device.online) throw new MockError(502, s.device.last_error ?? 'Sem resposta.');
			return { ...s.device, info: { ...s.device.info } };
		}
		case 'GET /rooms':
			return [...state.rooms].sort((a, b) => a.sort_order - b.sort_order);
		case 'POST /rooms': {
			const room = { id: state.nextId++, name: String(body.name).trim(), sort_order: state.rooms.length };
			state.rooms.push(room);
			emit('rooms');
			return room;
		}
		case 'PATCH /rooms/:id': {
			const room = state.rooms.find((r) => r.id === id)!;
			room.name = String(body.name).trim();
			emit('rooms');
			return room;
		}
		case 'PUT /rooms/order':
			(body.ids as number[]).forEach((rid, i) => {
				const room = state.rooms.find((r) => r.id === rid);
				if (room) room.sort_order = i;
			});
			emit('rooms');
			return [...state.rooms].sort((a, b) => a.sort_order - b.sort_order);
		case 'DELETE /rooms/:id':
			state.rooms = state.rooms.filter((r) => r.id !== id);
			for (const s of state.sims) if (s.device.room_id === id) s.device.room_id = null;
			emit('devices');
			return undefined;
		case 'POST /rooms/:id/power': {
			const targets = state.sims.filter(
				(s) => s.device.room_id === id && s.device.online && (body.on || !s.device.confirm_off)
			);
			targets.forEach((s) => setPower(s, !!body.on));
			return { changed: targets.length, failed: [] };
		}
		case 'GET /energy': {
			const key = (q.get('range') ?? 'today') as RangeKey;
			const roomId = q.get('room_id');
			const ids = roomId ? state.sims.filter((s) => s.device.room_id === Number(roomId)).map((s) => s.device.id) : undefined;
			return report(key, ids);
		}
		case 'GET /schedules':
			return schedules();
		case 'POST /schedules': {
			const d = sim(Number(body.device_id)).device;
			const s: Schedule = {
				id: state.nextId++,
				device_id: d.id,
				device_name: d.name,
				room_id: d.room_id,
				action: body.action,
				time: body.time,
				days: body.days,
				enabled: body.enabled ?? true,
				next_run: null,
				last_run_at: null,
				last_result: null
			};
			state.schedules.push(s);
			emit('schedules');
			return schedules().find((x) => x.id === s.id);
		}
		case 'PATCH /schedules/:id': {
			const s = state.schedules.find((x) => x.id === id);
			if (!s) throw new MockError(404, 'Agendamento não encontrado.');
			Object.assign(s, body);
			emit('schedules');
			return schedules().find((x) => x.id === id);
		}
		case 'DELETE /schedules/:id':
			state.schedules = state.schedules.filter((x) => x.id !== id);
			emit('schedules');
			return undefined;
		case 'GET /alerts': {
			const items = [...state.alerts]
				.filter((a) => q.get('filter') !== 'unread' || !a.acknowledged)
				.sort((a, b) => b.created_at - a.created_at);
			return { unread: unreadAlerts(), items };
		}
		case 'POST /alerts/:id/ack': {
			const a = state.alerts.find((x) => x.id === id);
			if (a) a.acknowledged = true;
			emit('alerts');
			return { unread: unreadAlerts() };
		}
		case 'POST /alerts/ack-all':
			state.alerts.forEach((a) => (a.acknowledged = true));
			emit('alerts');
			return { unread: 0 };
		case 'GET /settings':
			return state.settings;
		case 'PATCH /settings':
			Object.assign(state.settings, body);
			emit('energy');
			return state.settings;
		case 'GET /timezones':
			return ['America/Bahia', 'America/Belem', 'America/Fortaleza', 'America/Manaus', 'America/Recife', 'America/Sao_Paulo'];
		case 'GET /tuya':
			return {
				linked: state.tuya.linked,
				username: state.tuya.linked ? state.tuya.username : null,
				linked_at: state.tuya.linked ? state.tuya.linked_at : null,
				imported_devices: state.sims.length
			};
		case 'POST /tuya/login':
			if (String(body.user_code).trim().length < 4) throw new MockError(502, 'Código de usuário inválido. Confira no app Tuya Smart.');
			state.pendingLogin = { token: 'demo', started: now() };
			return { token: 'demo', qr_svg: fakeQr() };
		case 'GET /tuya/login/demo': {
			// No protótipo, a "leitura do QR code" é confirmada sozinha depois de alguns segundos.
			const linked = !!state.pendingLogin && now() - state.pendingLogin.started > 5;
			if (linked) {
				state.tuya = { linked: true, username: 'diego@exemplo.com', linked_at: now() };
				state.pendingLogin = null;
			}
			return { linked };
		}
		case 'GET /tuya/devices':
			await new Promise((r) => setTimeout(r, 2200));
			return candidates();
		case 'POST /tuya/import':
			return { imported: importDevices(body.devices) };
		case 'POST /tuya/rescan':
			await new Promise((r) => setTimeout(r, 1500));
			return { updated: 0 };
		case 'DELETE /tuya':
			state.tuya.linked = false;
			return undefined;
	}
	throw new MockError(404, 'Não encontrado.');
}

export async function mockRequest(method: string, path: string, body: unknown): Promise<{ status: number; data: unknown }> {
	await delay();
	try {
		const data = await handle(method, path, body ?? {});
		return { status: data === undefined ? 204 : 200, data };
	} catch (error) {
		if (error instanceof MockError) return { status: error.status, data: { detail: error.message } };
		throw error;
	}
}
