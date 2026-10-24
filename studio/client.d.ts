export type ModelId = 'generic' | 'sdxl' | 'flux' | 'qwen-image' | 'moss-image' | 'anima' | 'fibo' | 'fibo-edit' | (string & {});
export type StyleLayer = { id: string; intensity: number };
export type Recipe = { schema_version?: 1; prompt: string; negative?: string; model?: ModelId; styles?: StyleLayer[]; conflict_policy?: 'last_wins' | 'first_wins' | 'error'; locked_axes?: string[] };
export type StyleMetadata = { id: string; name: string; description: string; category: string; kind: 'style' | 'grade' | 'modifier'; tags: string[]; [key: string]: unknown };
export type ModelProfile = { id: string; name: string; format: 'natural' | 'tags' | 'structured'; negative: boolean; weighting: boolean; conditioning: 'clip' | 'specialized'; guidance: string; sources: string[]; evidence: 'documented' | 'conservative'; aliases: string[] };
export type Composition = { schema_version: 1; positive: string; negative: string; structured: Record<string, unknown>; recipe: Recipe; fingerprint: string; catalog_fingerprint: string; profile: string; warnings: { code: string; message: string }[]; trace: { style_id: string; axis: string; action: string; text: string; reason: string }[] };
export class PromptStylerClient {
  constructor(options?: { baseUrl?: string; fetchImpl?: typeof fetch; timeoutMs?: number });
  styles(filters?: { q?: string; category?: string; model?: ModelId; tag?: string | string[]; kind?: string; limit?: number; offset?: number }): Promise<{ items: StyleMetadata[]; catalog_fingerprint: string }>;
  style(id: string): Promise<StyleMetadata>;
  profiles(): Promise<{ items: ModelProfile[] }>;
  catalog(): Promise<{ schema_version: 1; catalog_fingerprint: string; total: number; categories: string[]; kinds: string[] }>;
  health(): Promise<{ status: 'ok'; schema_version: 1; catalog_fingerprint: string }>;
  compose(recipe: Recipe): Promise<Composition>;
  composeJson(rawText: string): Promise<Composition>;
  recommend(request: { prompt: string; model?: ModelId; limit?: number }): Promise<{ items: (StyleMetadata & { score: number; reasons: string[] })[] }>;
}
export function styleGenerationBody<T extends { prompt?: string; negative?: string }>(client: PromptStylerClient, body: T, recipe: Omit<Recipe, 'prompt'>): Promise<{ body: T & { prompt: string; negative: string }; composition: Composition }>;
