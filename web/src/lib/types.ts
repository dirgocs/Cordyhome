export type DeviceKind = 'plug' | 'light' | 'switch' | 'relay' | 'climate' | 'other';

/** O que o aparelho sabe fazer; a interface monta os controles a partir disso. */
export type Capability = 'power' | 'energy' | 'brightness' | 'color_temp' | 'color';

export interface Hsv {
	h: number;
	s: number;
	v: number;
}

export interface DeviceState {
	brightness?: number;
	color_temp?: number;
	color?: Hsv;
	mode?: string;
}

export interface Device {
	id: number;
	name: string;
	room_id: number | null;
	kind: DeviceKind;
	adapter: string;
	enabled: boolean;
	sort_order: number;
	online: boolean;
	is_on: boolean | null;
	power_w: number | null;
	power_estimated: boolean;
	voltage_v: number | null;
	current_a: number | null;
	last_seen: number | null;
	last_error: string | null;
	nominal_watts: number | null;
	power_alert_watts: number | null;
	confirm_off: boolean;
	capabilities: Capability[];
	state: DeviceState;
	info: {
		ip: string | null;
		protocol_version: number | null;
		product_name: string | null;
		has_energy_meter: boolean;
	};
}

export interface Room {
	id: number;
	name: string;
	sort_order: number;
}

export type Action = 'on' | 'off' | 'toggle';

export interface Schedule {
	id: number;
	device_id: number;
	device_name: string;
	room_id: number | null;
	action: Action;
	time: string;
	days: number;
	enabled: boolean;
	next_run: string | null;
	last_run_at: number | null;
	last_result: string | null;
}

export interface HomeData {
	power_w: number;
	power_history: { ts: number; w: number }[];
	today: { kwh: number; cost: number };
	month: { kwh: number; cost: number; projected_cost: number | null };
	counts: { total: number; online: number; on: number };
	unread_alerts: number;
	next_schedules: Schedule[];
	rooms: Room[];
	devices: Device[];
	tariff_per_kwh: number;
}

export interface SeriesPoint {
	start: string;
	kwh: number;
}

export type RangeKey = 'today' | 'yesterday' | '7d' | '30d' | 'month' | '12m';

export interface EnergyReport {
	range: RangeKey;
	bucket: 'hour' | 'day' | 'month';
	start: string;
	end: string;
	total_kwh: number;
	cost: number;
	projected_kwh: number | null;
	projected_cost: number | null;
	series: SeriesPoint[];
	devices: { device_id: number; name: string; room_id: number | null; kwh: number; cost: number }[];
	rooms: { room_id: number | null; kwh: number; cost: number }[];
	tariff_per_kwh: number;
}

export interface DeviceDetail extends Device {
	energy: {
		today_kwh: number;
		today_cost: number;
		month_kwh: number;
		month_cost: number;
		projected_cost: number | null;
		daily: SeriesPoint[];
	};
	power_history: { ts: number; avg_w: number }[];
	schedules: Schedule[];
	events: { ts: number; source: string; action: string; detail: string | null }[];
}

export interface Alert {
	id: number;
	device_id: number | null;
	device_name: string | null;
	kind: 'offline' | 'high_power' | 'command_failed' | 'schedule_failed' | string;
	severity: 'info' | 'warning' | 'critical';
	message: string;
	created_at: number;
	resolved_at: number | null;
	acknowledged: boolean;
}

export interface Settings {
	tariff_per_kwh: number;
	timezone: string;
	poll_interval_sec: number;
	offline_after_failures: number;
	lan_networks: string[];
}

export interface TuyaStatus {
	linked: boolean;
	username: string | null;
	linked_at: number | null;
	imported_devices: number;
}

export interface TuyaCandidate {
	id: string;
	name: string;
	room: string | null;
	kind: DeviceKind;
	product_name: string;
	cloud_online: boolean;
	local_supported: boolean;
	has_energy_meter: boolean;
	lan_ip: string | null;
	imported_device_id: number | null;
}

export interface MqttStatus {
	linked: boolean;
	enabled: boolean;
	mode: 'embedded' | 'external';
	connected: boolean;
	error: string | null;
	host: string;
	port: number;
	username: string;
	/** Só no servidor embutido: é o que o usuário digita no aparelho. */
	password: string | null;
	/** IPs deste computador, para o servidor embutido. */
	addresses: string[];
	discovery_prefix: string;
	discovered_devices: number;
	imported_devices: number;
}

export interface MqttCandidate {
	id: string;
	name: string;
	kind: DeviceKind;
	product_name: string | null;
	capabilities: Capability[];
	has_energy_meter: boolean;
	imported_device_id: number | null;
}
