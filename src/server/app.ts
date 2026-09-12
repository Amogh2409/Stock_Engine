import path from 'node:path';
import type { Server } from 'node:http';

import express, { type Express, type RequestHandler } from 'express';

export interface ServerOptions {
  port?: number;
  host?: string;
  /** Serve the built client (true) or hand requests to the dev middleware (false). */
  production?: boolean;
  /** Directory holding the built client. Defaults to clientDirFor(entry directory). */
  clientDir?: string;
  /** Supplies the dev middleware (Vite), injected so tests need no bundler. */
  devMiddleware?: () => Promise<RequestHandler>;
}

/**
 * Where the built client lives, given the directory the server bundle runs
 * from: <root>/dist-server/server.cjs serves <root>/dist. Derived from the
 * bundle rather than the working directory, so starting the server from another
 * folder still finds the client.
 */
export function clientDirFor(bundleDir: string): string {
  return path.resolve(bundleDir, '..', 'dist');
}

/** Directory of the script node was started with. */
export function entryDir(): string {
  return path.dirname(process.argv[1] ?? process.cwd());
}

/**
 * Paths that must never be served even if a build drops them next to the
 * client. The server bundle is built to dist-server/ precisely so this cannot
 * happen; this is the second lock.
 */
const NEVER_SERVED = new Set(['/server.cjs', '/server.cjs.map', '/server.js', '/server.js.map']);

export async function createApp(options: ServerOptions = {}): Promise<Express> {
  const production = options.production ?? process.env.NODE_ENV === 'production';
  const app = express();

  app.get('/api/health', (_req, res) => {
    res.json({ status: 'ok' });
  });

  if (production) {
    const clientDir = options.clientDir ?? clientDirFor(entryDir());
    app.use((req, res, next) => {
      if (NEVER_SERVED.has(req.path)) {
        res.status(404).json({ error: 'Not found' });
        return;
      }
      next();
    });
    app.use(express.static(clientDir));
    // Unknown API routes are a 404, not the SPA page: an API client must not
    // have to parse HTML to discover that a route does not exist.
    app.use('/api', (_req, res) => {
      res.status(404).json({ error: 'Unknown API route' });
    });
    app.get('*all', (_req, res) => {
      res.sendFile(path.join(clientDir, 'index.html'));
    });
  } else {
    if (!options.devMiddleware) throw new Error('a dev server needs devMiddleware');
    app.use(await options.devMiddleware());
  }

  return app;
}

/**
 * Listen, resolving only once the socket is actually open. Express passes a
 * listen failure (a busy port, say) to the error event; ignoring it used to
 * print "Server running on ..." and exit 0 without a server.
 */
export async function startServer(options: ServerOptions = {}): Promise<Server> {
  const production = options.production ?? process.env.NODE_ENV === 'production';
  // Dev serves source files and the Vite middleware, so it stays on loopback;
  // only the production server listens on every interface.
  const host = options.host ?? (production ? '0.0.0.0' : '127.0.0.1');
  const port = options.port ?? (process.env.PORT ? Number(process.env.PORT) : 3000);
  const app = await createApp({ ...options, production });

  return new Promise<Server>((resolve, reject) => {
    const server = app.listen(port, host);
    const onError = (error: NodeJS.ErrnoException) => {
      server.removeListener('listening', onListening);
      reject(error);
    };
    const onListening = () => {
      server.removeListener('error', onError);
      resolve(server);
    };
    server.once('error', onError);
    server.once('listening', onListening);
  });
}
