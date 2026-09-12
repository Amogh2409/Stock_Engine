import type { RequestHandler } from 'express';

import { clientDirFor, entryDir, startServer } from './src/server/app';

const production = process.env.NODE_ENV === 'production';

startServer({
  production,
  clientDir: production ? clientDirFor(entryDir()) : undefined,
  devMiddleware: production
    ? undefined
    : async () => {
        const { createServer: createViteServer } = await import('vite');
        const vite = await createViteServer({
          server: { middlewareMode: true },
          appType: 'spa',
        });
        return vite.middlewares as unknown as RequestHandler;
      },
})
  .then((server) => {
    const address = server.address();
    const port = address !== null && typeof address !== 'string' ? address.port : '?';
    console.log(
      production
        ? `Server running on http://0.0.0.0:${port} (all interfaces)`
        : `Server running on http://127.0.0.1:${port}`,
    );
  })
  .catch((error: NodeJS.ErrnoException) => {
    const reason = error.code === 'EADDRINUSE' ? 'that port is already in use' : error.message;
    console.error(`Could not start the server: ${reason}`);
    process.exitCode = 1;
  });
