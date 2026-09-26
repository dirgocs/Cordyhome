/** Escala "bonita" para eixos: 0, 250, 500… ou 0, 0.5, 1… */
export function niceTicks(max: number, count = 4): number[] {
	if (!(max > 0)) return [0, 1];
	const raw = max / count;
	const magnitude = 10 ** Math.floor(Math.log10(raw));
	const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) ?? raw;
	const ticks: number[] = [];
	for (let v = 0; v <= max + step * 0.001; v += step) ticks.push(+v.toFixed(10));
	if (ticks[ticks.length - 1] < max) ticks.push(+(ticks[ticks.length - 1] + step).toFixed(10));
	return ticks;
}
