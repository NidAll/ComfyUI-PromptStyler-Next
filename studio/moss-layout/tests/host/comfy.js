// Test stand-in for HEISS server/comfy.js. The tests inject their own request functions.
export const comfyUrl = 'http://127.0.0.1:8188';

export async function comfy() {
  throw new Error('Test stand-in: inject a request function.');
}
