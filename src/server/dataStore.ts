import fs from 'node:fs';
import path from 'node:path';

import type { Express } from 'express';

/**
 * Serving the CLI's own inputs to the browser app.
 *
 * The two surfaces had no connection: `python/engine.py` writes to
 * `data-store/`, and the React app only ever knew what a human dragged into it,
 * so opening the page after a CLI run showed `bundled_sample.csv` -- invented
 * figures, no prices, no position sizes -- with nothing on screen saying the
 * data on disk was different. Re-uploading two files by hand every session was
 * the only way to see a real run.
 *
 * These routes close that gap: the app asks what is on disk at boot and loads
 * it. The engine's rule is copied exactly -- NEWEST FILE WINS -- so the page and
 * the CLI agree about which export is current rather than disagreeing quietly.
 */

/** What the app needs to decide whether to load anything, and to say where it came from. */
export interface DataStoreFile {
  name: string;
  modifiedMs: number;
  bytes: number;
}

export interface DataStoreSnapshot {
  available: boolean;
  root: string;
  fundamentals: DataStoreFile | null;
  prices: DataStoreFile | null;
}

/**
 * Where the engine keeps its data, resolved the same way `resolve_data_root`
 * does in engine.py: the environment variable first, then `<root>/data-store`.
 * The Colab branch has no meaning here because this only ever runs on the
 * machine serving the page.
 *
 * Deliberately NOT derived from the working directory: `npm run dev` is run
 * from the repo root, but a server started from elsewhere must still find the
 * same folder the CLI wrote to.
 */
export function dataStoreRoot(repoRoot: string): string {
  const configured = process.env.TRADEBOT_DATA_DIR;
  return configured && configured.trim() !== ''
    ? path.resolve(configured)
    : path.resolve(repoRoot, 'data-store');
}

/**
 * Newest `.csv` directly inside `dir`, or null.
 *
 * Only regular files at the top level are considered, which is what keeps
 * `data-store/fundamentals/archive/` -- the point-in-time archive, holding one
 * dated copy of every export ever used -- from being mistaken for the current
 * export.
 */
export function newestCsv(dir: string): (DataStoreFile & { path: string }) | null {
  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    // An absent directory is the normal state, not a fault: data-store/** is
    // gitignored, so a fresh clone has none of this.
    return null;
  }

  let best: (DataStoreFile & { path: string }) | null = null;
  for (const entry of entries) {
    if (!entry.isFile() || !entry.name.toLowerCase().endsWith('.csv')) continue;
    const full = path.join(dir, entry.name);
    let stat: fs.Stats;
    try {
      stat = fs.statSync(full);
    } catch {
      continue;
    }
    if (best === null || stat.mtimeMs > best.modifiedMs) {
      best = { name: entry.name, modifiedMs: stat.mtimeMs, bytes: stat.size, path: full };
    }
  }
  return best;
}

/** What is on disk right now. Absence is reported, never thrown. */
export function readDataStore(root: string): DataStoreSnapshot {
  const fundamentals = newestCsv(path.join(root, 'fundamentals'));
  const prices = newestCsv(path.join(root, 'market_data'));
  const strip = (file: (DataStoreFile & { path: string }) | null): DataStoreFile | null =>
    file === null ? null : { name: file.name, modifiedMs: file.modifiedMs, bytes: file.bytes };
  return {
    // Fundamentals alone are enough to be useful: prices only add the technical
    // half, and the app already renders honestly without them.
    available: fundamentals !== null,
    root,
    fundamentals: strip(fundamentals),
    prices: strip(prices),
  };
}

/**
 * Mount the read-only data-store routes.
 *
 * DEV ONLY, and that is a security decision rather than an oversight. The dev
 * server binds 127.0.0.1; the production server binds 0.0.0.0. These routes
 * serve a person's own holdings and fundamentals off their disk, which is fine
 * on loopback and is not fine to every machine on the network. If this is ever
 * wanted in production it needs authentication first, not just a flag.
 *
 * No route takes a filename from the client. Paths are only ever built from a
 * directory listing of a fixed folder, so there is nothing for a traversal
 * attempt to reach.
 */
export function mountDataStoreRoutes(app: Express, repoRoot: string): void {
  const root = dataStoreRoot(repoRoot);

  app.get('/api/data-store', (_req, res) => {
    res.json(readDataStore(root));
  });

  const sendNewest = (dir: string, label: string) => (_req: unknown, res: import('express').Response) => {
    const file = newestCsv(path.join(root, dir));
    if (file === null) {
      res.status(404).json({ error: `No ${label} CSV in ${path.join(root, dir)}` });
      return;
    }
    // text/csv rather than a download: the app fetches this, it does not save it.
    res.type('text/csv');
    res.setHeader('X-Data-Store-File', file.name);
    res.sendFile(file.path);
  };

  app.get('/api/data-store/fundamentals', sendNewest('fundamentals', 'fundamentals'));
  app.get('/api/data-store/prices', sendNewest('market_data', 'price-history'));
}
