const nf = (digits: number) =>
	new Intl.NumberFormat('pt-BR', { minimumFractionDigits: digits, maximumFractionDigits: digits });

const brl = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });

/** Potência compacta: "8,4 W", "95 W", "1,24 kW". */
export function watts(value: number | null | undefined): string {
	if (value == null) return '—';
	if (value >= 1000) return `${nf(value >= 10000 ? 1 : 2).format(value / 1000)} kW`;
	if (value < 10) return `${nf(1).format(value)} W`;
	return `${nf(0).format(value)} W`;
}

/** Separa número e unidade, para compor números grandes com unidade menor. */
export function wattsParts(value: number | null | undefined): [string, string] {
	const [num, unit] = watts(value).split(' ');
	return [num, unit ?? ''];
}

export function kwh(value: number | null | undefined): string {
	if (value == null) return '—';
	const digits = value < 1 ? 2 : value < 100 ? 1 : 0;
	return `${nf(digits).format(value)} kWh`;
}

export function money(value: number | null | undefined): string {
	return value == null ? '—' : brl.format(value);
}

export function number(value: number, digits = 0): string {
	return nf(digits).format(value);
}

export function volts(value: number | null): string {
	return value == null ? '—' : `${nf(0).format(value)} V`;
}

export function amps(value: number | null): string {
	return value == null ? '—' : `${nf(2).format(value)} A`;
}

const rtf = new Intl.RelativeTimeFormat('pt-BR', { numeric: 'auto' });

export function relative(ts: number | null | undefined, now = Date.now() / 1000): string {
	if (!ts) return 'nunca';
	const diff = ts - now;
	const abs = Math.abs(diff);
	if (abs < 45) return 'agora';
	if (abs < 3600) return rtf.format(Math.round(diff / 60), 'minute');
	if (abs < 86400) return rtf.format(Math.round(diff / 3600), 'hour');
	if (abs < 86400 * 7) return rtf.format(Math.round(diff / 86400), 'day');
	return dateShort(ts * 1000);
}

export function dateShort(value: string | number | Date): string {
	return new Date(value).toLocaleDateString('pt-BR', { day: 'numeric', month: 'short' });
}

export function timeOf(value: string | number | Date): string {
	return new Date(value).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}

export function dateTime(ts: number): string {
	return new Date(ts * 1000).toLocaleString('pt-BR', {
		day: 'numeric',
		month: 'short',
		hour: '2-digit',
		minute: '2-digit'
	});
}

// Dias da semana: bit 0 = domingo … bit 6 = sábado (mesmo formato do hub).
export const WEEKDAYS = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'];
export const WEEKDAY_INITIALS = ['D', 'S', 'T', 'Q', 'Q', 'S', 'S'];
export const ALL_DAYS = 0b1111111;
export const WORKDAYS = 0b0111110;
export const WEEKEND = 0b1000001;

export function daysLabel(days: number): string {
	if (days === ALL_DAYS) return 'Todos os dias';
	if (days === WORKDAYS) return 'Dias úteis';
	if (days === WEEKEND) return 'Fins de semana';
	return WEEKDAYS.filter((_, i) => days & (1 << i)).join(', ');
}

export function nextRunLabel(iso: string | null): string {
	if (!iso) return 'Pausado';
	const date = new Date(iso);
	const today = new Date();
	const tomorrow = new Date();
	tomorrow.setDate(today.getDate() + 1);
	const same = (a: Date, b: Date) => a.toDateString() === b.toDateString();
	// O horário já aparece em destaque na linha; aqui basta o dia.
	if (same(date, today)) return 'Próxima hoje';
	if (same(date, tomorrow)) return 'Próxima amanhã';
	return `Próxima ${WEEKDAYS[date.getDay()].toLowerCase()}`;
}

/** Rótulos curtos (eixo) e longos (tooltip) para os buckets de energia. */
export function bucketLabels(iso: string, bucket: 'hour' | 'day' | 'month'): [string, string] {
	const d = new Date(iso);
	if (bucket === 'hour') {
		const h = d.getHours();
		return [`${h}h`, `${String(h).padStart(2, '0')}:00 – ${String((h + 1) % 24).padStart(2, '0')}:00`];
	}
	if (bucket === 'day') {
		return [
			String(d.getDate()),
			d.toLocaleDateString('pt-BR', { weekday: 'short', day: 'numeric', month: 'short' })
		];
	}
	return [
		d.toLocaleDateString('pt-BR', { month: 'short' }).replace('.', ''),
		d.toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' })
	];
}

export function kwhTick(value: number): string {
	return value === 0 ? '0' : nf(value < 1 ? 1 : 0).format(value);
}

export function wattsTick(value: number): string {
	if (value === 0) return '0';
	if (value >= 1000) return `${nf(value % 1000 ? 1 : 0).format(value / 1000)} kW`;
	return `${nf(0).format(value)} W`;
}
