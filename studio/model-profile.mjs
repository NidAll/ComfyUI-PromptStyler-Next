/** Host metadata mapping only; prompt composition belongs to the Python engine. */
export function studioModelProfile(profile) {
  const explicit = profile?.promptStyler?.model;
  if (explicit) return explicit;
  const family = String(profile?.family || '').toLowerCase().replaceAll('_', '-');
  const cfg = Number(profile?.defaults?.cfg ?? 1);
  if (family === 'anima') return cfg <= 1 ? 'anima-turbo' : 'anima';
  if (family === 'moss-image') return cfg <= 1 ? 'moss-image-dmd' : 'moss-image';
  if (family === 'fibo2' || family === 'fibo') return profile?.capabilities?.imageToImage ? 'fibo-edit' : 'fibo';
  if (family === 'sdxl') return 'sdxl';
  if (family.startsWith('flux')) return 'flux';
  if (family === 'qwen-image-2.1' || family === 'qwen-image-21') return 'qwen-image-2.1';
  if (family === 'qwen-image') return 'qwen-image';
  return 'generic';
}
