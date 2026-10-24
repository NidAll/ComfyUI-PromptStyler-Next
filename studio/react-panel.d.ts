import type * as React from 'react';
import type { Recipe } from './client.mjs';
import type { StudioProfile } from './model-profile.mjs';
export function createPromptStylerPanel(runtime: typeof React): React.ComponentType<{ profile?: StudioProfile; prompt?: string; negative?: string; mode?: 'image' | 'video' }>;
export function studioPromptStylerSelection(profile?: StudioProfile): Omit<Recipe, 'prompt' | 'negative'> | undefined;
