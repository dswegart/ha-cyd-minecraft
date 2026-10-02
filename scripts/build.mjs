import { build } from 'esbuild';
import { readFileSync } from 'node:fs';

const license = readFileSync(new URL('../licenses/qrcode-generator.txt', import.meta.url), 'utf8');
await build({
  entryPoints: ['dashboard/src/card.js'],
  outfile: 'dashboard/minecraft-cyd-card.js',
  bundle: true, format: 'iife', minify: true, legalComments: 'inline',
  banner: { js: `/*! qrcode-generator 2.0.4\n${license.replaceAll('*/', '* /')}\n*/` },
});
