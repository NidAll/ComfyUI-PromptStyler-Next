import type * as React from 'react';
import type { Recipe } from './client.mjs';
import type { StudioProfile } from './model-profile.mjs';
export function createPromptStylerPanel(runtime: typeof React): React.ComponentType<{ profile?: StudioProfile; prompt?: string; negative?: string; mode?: 'image' | 'video' }>;
export function studioPromptStylerSelection(profile?: StudioProfile): Omit<Recipe, 'prompt' | 'negative'> | undefined;

export function restoreStudioPromptStylerSelection(profile: StudioProfile | undefined, recipe?: Omit<Recipe, 'prompt' | 'negative'> | null): void;
export type StudioStyleState = { enabled: boolean; styles: Array<{id: string; name?: string; kind?: 'style' | 'grade' | 'modifier'; intensity: number}>; model: string; conflict_policy: 'last_wins' | 'first_wins' | 'error'; locked_axes: string[]; mix: boolean };
export function getStudioPromptStylerState(profile?: StudioProfile): StudioStyleState;
export function restoreStudioPromptStylerState(profile: StudioProfile | undefined, state?: StudioStyleState | null): void;
