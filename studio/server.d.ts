import type { IncomingMessage, ServerResponse } from 'node:http';
import type { Composition, Recipe } from './client.mjs';
export function createManagedPromptStyler(options?: { python?: string; projectRoot?: string; startupTimeoutMs?: number }): {
  middleware(req: IncomingMessage & { body?: unknown }, res: ServerResponse): Promise<void>;
  compose(recipe: Recipe): Promise<Composition>;
  stop(): boolean | undefined;
  close(): Promise<void>;
};
