// @vitest-environment node
/**
 * The production server, driven over a real socket. No test-only HTTP client is
 * added: node:http and node:net are enough to prove what the fixes claim.
 */
import { mkdirSync, mkdtempSync, utimesSync, writeFileSync } from 'node:fs';
import { get as httpGet, Server } from 'node:http';
import { createServer as createSocketServer } from 'node:net';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { clientDirFor, startServer } from '../server/app';

const running: Server[] = [];

afterEach(async () => {
  while (running.length > 0) {
    const server = running.pop()!;
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});

/** A dist-like directory holding the client build and, deliberately, a server bundle. */
function fakeClientDir(): string {
  const dir = mkdtempSync(path.join(tmpdir(), 'screener-dist-'));
  writeFileSync(path.join(dir, 'index.html'), '<!doctype html><title>app</title>');
  writeFileSync(path.join(dir, 'server.cjs'), 'throw new Error("server bundle");');
  writeFileSync(path.join(dir, 'server.cjs.map'), '{"version":3}');
  return dir;
}

function request(port: number, urlPath: string): Promise<{ status: number; body: string; type: string }> {
  return new Promise((resolve, reject) => {
    httpGet({ host: '127.0.0.1', port, path: urlPath }, (response) => {
      let body = '';
      response.on('data', (chunk) => {
        body += chunk;
      });
      response.on('end', () =>
        resolve({
          status: response.statusCode ?? 0,
          body,
          type: String(response.headers['content-type'] ?? ''),
        }),
      );
    }).on('error', reject);
  });
}

async function serve(clientDir: string): Promise<number> {
  const server = await startServer({ port: 0, clientDir, production: true });
  running.push(server);
  const address = server.address();
  if (address === null || typeof address === 'string') throw new Error('no port');
  return address.port;
}

describe('Production server', () => {
  it('fails loudly when the port is busy instead of reporting success', async () => {
    // The blocker must hold the same interface the server will bind: on macOS
    // 127.0.0.1 and 0.0.0.0 are different bindings and would not collide.
    const blocker = createSocketServer();
    const port = await new Promise<number>((resolve) => {
      blocker.listen(0, '0.0.0.0', () => {
        const address = blocker.address();
        resolve(typeof address === 'object' && address !== null ? address.port : 0);
      });
    });
    await expect(
      startServer({ port, clientDir: fakeClientDir(), production: true }),
    ).rejects.toMatchObject({ code: 'EADDRINUSE' });
    await new Promise<void>((resolve) => blocker.close(() => resolve()));
  });

  it('serves the app but never the server bundle or its source map', async () => {
    const port = await serve(fakeClientDir());
    expect((await request(port, '/')).status).toBe(200);
    expect((await request(port, '/index.html')).status).toBe(200);
    for (const leak of ['/server.cjs', '/server.cjs.map']) {
      const response = await request(port, leak);
      expect(response.status, leak).toBe(404);
      expect(response.body, leak).not.toContain('server bundle');
    }
  });

  it('answers unknown /api routes with 404 JSON, not the SPA page', async () => {
    const port = await serve(fakeClientDir());
    const health = await request(port, '/api/health');
    expect(health.status).toBe(200);
    expect(JSON.parse(health.body)).toEqual({ status: 'ok' });

    const missing = await request(port, '/api/does-not-exist');
    expect(missing.status).toBe(404);
    expect(missing.type).toMatch(/application\/json/);
    expect(missing.body).not.toContain('<!doctype html');
  });

  it('still serves SPA routes from index.html', async () => {
    const port = await serve(fakeClientDir());
    const deep = await request(port, '/inspection/nested/spa-route');
    expect(deep.status).toBe(200);
    expect(deep.body).toContain('<title>app</title>');
  });
});

describe('Server binding and paths', () => {
  it('binds only the loopback interface in dev', async () => {
    const server = await startServer({
      port: 0,
      production: false,
      // Stand in for the Vite middleware, which the dev server would attach.
      devMiddleware: async () => (_req, _res, next) => next(),
    });
    running.push(server);
    const address = server.address();
    expect(address !== null && typeof address !== 'string' ? address.address : '').toBe('127.0.0.1');
  });

  it('binds all interfaces in production, where that is the point', async () => {
    const server = await startServer({ port: 0, clientDir: fakeClientDir(), production: true });
    running.push(server);
    const address = server.address();
    expect(address !== null && typeof address !== 'string' ? address.address : '').toBe('0.0.0.0');
  });

  it('derives the client directory from the bundle, not the working directory', () => {
    expect(clientDirFor('/somewhere/app/dist-server')).toBe(path.resolve('/somewhere/app/dist'));
    expect(clientDirFor('/other/place/dist-server')).toBe(path.resolve('/other/place/dist'));
  });
});

describe('Serving the CLI data-store to the app', () => {
  /**
   * A data-store laid out the way engine.py writes one, including the archive
   * subdirectory that must never be mistaken for the current export.
   */
  function fakeDataStore(options: { archive?: boolean; prices?: boolean } = {}): string {
    const root = mkdtempSync(path.join(tmpdir(), 'screener-datastore-'));
    const fundamentals = path.join(root, 'data-store', 'fundamentals');
    mkdirSync(fundamentals, { recursive: true });
    writeFileSync(path.join(fundamentals, 'older_export.csv'), 'Name,NSE code\nOld Ltd.,OLD\n');
    // Two exports, written in order: the newer must win, as it does in the CLI.
    const newer = path.join(fundamentals, 'newer_export.csv');
    writeFileSync(newer, 'Name,NSE code\nNew Ltd.,NEW\n');
    utimesSync(newer, new Date(), new Date(Date.now() + 60_000));

    if (options.archive !== false) {
      const archive = path.join(fundamentals, 'archive', '2026-09');
      mkdirSync(archive, { recursive: true });
      // Dated far in the future, so a listing that recursed would pick it.
      const archived = path.join(archive, '2026-09-11_deadbeef.csv');
      writeFileSync(archived, 'Name,NSE code\nArchived Ltd.,ARCHIVE\n');
      utimesSync(archived, new Date(), new Date(Date.now() + 600_000));
    }
    if (options.prices !== false) {
      const market = path.join(root, 'data-store', 'market_data');
      mkdirSync(market, { recursive: true });
      writeFileSync(
        path.join(market, 'price_history_20260916.csv'),
        'Date,Ticker,Open,High,Low,Close,Volume\n2026-09-15,NEW,1,1,1,1,10\n',
      );
    }
    return root;
  }

  async function serveDev(repoRoot: string): Promise<number> {
    const server = await startServer({
      port: 0,
      production: false,
      repoRoot,
      devMiddleware: async () => (_req, res) => {
        res.status(200).send('<!doctype html><title>dev</title>');
      },
    });
    running.push(server);
    const address = server.address();
    if (address === null || typeof address === 'string') throw new Error('no port');
    return address.port;
  }

  it('reports the newest export and serves it', async () => {
    const port = await serveDev(fakeDataStore());
    const index = JSON.parse((await request(port, '/api/data-store')).body);
    expect(index.available).toBe(true);
    expect(index.fundamentals.name).toBe('newer_export.csv');
    expect(index.prices.name).toBe('price_history_20260916.csv');

    const csv = await request(port, '/api/data-store/fundamentals');
    expect(csv.status).toBe(200);
    expect(csv.body).toContain('New Ltd.');
    expect(csv.body).not.toContain('Old Ltd.');
  });

  it('never mistakes the point-in-time archive for the current export', async () => {
    // The archive holds a dated copy of every export ever used and is stamped
    // NEWER than the live file here, so a recursive or mtime-only search would
    // serve it. Screening against an archived vintage would look like a normal
    // run and be wrong about today.
    const port = await serveDev(fakeDataStore({ archive: true }));
    const index = JSON.parse((await request(port, '/api/data-store')).body);
    expect(index.fundamentals.name).toBe('newer_export.csv');
    expect((await request(port, '/api/data-store/fundamentals')).body).not.toContain('Archived Ltd.');
  });

  it('reports an absent data-store as unavailable rather than failing', async () => {
    // data-store/** is gitignored, so a fresh clone has none of this. The app
    // must fall back to the bundled sample, not show an error.
    const empty = mkdtempSync(path.join(tmpdir(), 'screener-nodata-'));
    const port = await serveDev(empty);
    const index = await request(port, '/api/data-store');
    expect(index.status).toBe(200);
    expect(JSON.parse(index.body)).toMatchObject({ available: false, fundamentals: null, prices: null });
    expect((await request(port, '/api/data-store/fundamentals')).status).toBe(404);
  });

  it('does NOT serve the data-store in production', async () => {
    // The production server binds 0.0.0.0. These routes serve a person's own
    // holdings off their disk, which is safe on loopback and is not safe to
    // every machine on the network.
    const port = await serve(fakeClientDir());
    const index = await request(port, '/api/data-store');
    expect(index.status).toBe(404);
    expect(index.type).toMatch(/application\/json/);
  });
});
