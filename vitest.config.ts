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
    // Without an explicit exclude, vitest walks .claude/worktrees/ -- a live
    // git worktree of this same repository -- and collects every test file a
    // second time. That reported 12 files and 468 tests where there are 6 and
    // 234, and it would double a genuine failure count just as silently. The
    // directory is hidden from git by .git/info/exclude, which vitest does not
    // read, so it has to be named here as well.
    exclude: [
      '**/node_modules/**',
      '**/dist/**',
      '**/.claude/**',
    ],
  },
});
