import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    // The cross-engine parity suite spawns Python and imports pandas in
    // beforeAll. On a cold virtualenv that first import alone can take tens of
    // seconds, so the default 10s hook timeout is far too tight and produced a
    // spurious failure in the release gate.
    hookTimeout: 180_000,
    testTimeout: 60_000,
  },
});
