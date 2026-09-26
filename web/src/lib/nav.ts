/**
 * Caminho interno do app. No build de protótipo (artefato), a navegação usa o hash
 * (`#/energia`), porque a página é servida de um endereço que não controlamos.
 */
export const PROTOTYPE = import.meta.env.VITE_PROTOTYPE === '1';

export function to(path: string): string {
	return PROTOTYPE ? `#${path}` : path;
}
