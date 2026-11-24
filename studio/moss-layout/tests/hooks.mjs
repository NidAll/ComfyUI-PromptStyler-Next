const API = new URL('../api/', import.meta.url).href;
const HOST = /^\.\.\/server\/(comfy|comfy-queue|jobs)\.js$/;

export async function resolve(specifier, context, next) {
  const match = HOST.exec(specifier);
  if (match && context.parentURL?.startsWith(API)) {
    return { url: new URL(`./host/${match[1]}.js`, import.meta.url).href, shortCircuit: true };
  }
  return next(specifier, context);
}
