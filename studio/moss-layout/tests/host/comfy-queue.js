// Test stand-in for HEISS server/comfy-queue.js. The tests inject their own cancel and tracker.
export async function cancelPrompt() {
  throw new Error('Test stand-in: inject a cancel function.');
}

export function promptTracker() {
  throw new Error('Test stand-in: inject a prompt tracker.');
}
