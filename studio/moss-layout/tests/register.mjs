// Runs the overlay's tests outside a HEISS install: `../server/*.js` imports from api/ resolve to the
// small stand-ins in tests/host/. The stand-ins are for tests only; never copy them into HEISS.
import { register } from 'node:module';

register(new URL('./hooks.mjs', import.meta.url));
