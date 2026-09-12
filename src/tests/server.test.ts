// @vitest-environment node
/**
 * The production server, driven over a real socket. No test-only HTTP client is
 * added: node:http and node:net are enough to prove what the fixes claim.
 */
import { mkdtempSync, writeFileSync } from 'node:fs';
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
