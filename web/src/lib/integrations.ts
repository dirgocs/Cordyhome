/**
 * Integrações: de onde vêm os aparelhos. O fluxo de adicionar é o mesmo para qualquer marca
 * ou tipo; cada integração só traz o próprio passo a passo de conexão.
 */
export interface Integration {
	id: string;
	name: string;
	/** Marcas e apps cobertos. */
	brands: string;
	/** Tipos de aparelho que dá para trazer. */
	kinds: string;
	/** Página de conexão. */
	href: string;
	/** Endpoint de status (`{ linked, imported_devices, ... }`). */
	statusPath: string;
	/** Como chamar o estado "ligado" desta integração na lista. */
	linkedLabel: string;
}

export const INTEGRATIONS: Integration[] = [
	{
		id: 'tuya',
		name: 'Tuya / Smart Life',
		brands: 'Aparelhos controlados pelos apps Tuya Smart ou Smart Life, de várias marcas.',
		kinds: 'Tomadas, interruptores e outros aparelhos com controle local',
		href: '/adicionar/tuya',
		statusPath: '/tuya',
		linkedLabel: 'Conta vinculada'
	},
	{
		id: 'mqtt',
		name: 'MQTT',
		brands: 'SONOFF OpenEdge, Tasmota, ESPHome, Shelly, Zigbee2MQTT e outros que usam a descoberta do Home Assistant.',
		kinds: 'Relés, tomadas, interruptores, lâmpadas e medidores de energia',
		href: '/adicionar/mqtt',
		statusPath: '/mqtt',
		linkedLabel: 'Ativado'
	}
];
