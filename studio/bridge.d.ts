import type { IncomingMessage, ServerResponse } from 'node:http';
export function createPromptStylerBridge(options?: { upstream?: string; timeoutMs?: number; maxBodyBytes?: number; fetchImpl?: typeof fetch }): (req: IncomingMessage, res: ServerResponse) => Promise<void>;
