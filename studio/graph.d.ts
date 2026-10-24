import type { Recipe } from './client.mjs';
export type NativeGraph = Record<string, { class_type?: string; inputs: Record<string, unknown>; _meta?: Record<string, unknown> }>;
export type TextMapping = { node: string; input: string };
export function injectPromptStyler(graph: NativeGraph, workflow: { promptStyler?: TextMapping; controls?: { prompt?: TextMapping; negative?: TextMapping } }, body: { promptStyler?: Recipe; negative?: string }): NativeGraph;
