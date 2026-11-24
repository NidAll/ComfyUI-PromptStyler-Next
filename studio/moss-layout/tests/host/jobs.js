// Test stand-in for HEISS server/jobs.js.
export const jobs = new Map();

export function setTerminalJob(id, patch) {
  jobs.set(id, { ...jobs.get(id), ...patch, terminalAt: Date.now() });
}
