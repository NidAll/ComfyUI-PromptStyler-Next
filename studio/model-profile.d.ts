export type StudioProfile = {
  id?: string; profileId?: string; family?: string; kind?: 'image' | 'video';
  defaults?: { cfg?: number };
  capabilities?: { imageToImage?: boolean; promptFromImage?: boolean };
  promptStyler?: { model?: string };
};
export function studioModelProfile(profile?: StudioProfile): string;
