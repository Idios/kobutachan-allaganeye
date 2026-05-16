// AUTO-GENERATED CODE LIVES ELSEWHERE -- this script *produces* it.
// Generates gui/src/types/metadata.generated.ts from
// schemas/metadata.schema.json (issue #612). Resolved relative to this
// file so it works whether invoked via `npm run generate-types` (cwd
// = gui/) or via the Python orchestrator at scripts/codegen/generate.py.
import { compile } from 'json-schema-to-typescript';
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, '..', '..');
const schemaPath = resolve(repoRoot, 'schemas', 'metadata.schema.json');
const outPath = resolve(repoRoot, 'gui', 'src', 'types', 'metadata.generated.ts');

// The eslint config ignores this output path, so we don't need an
// eslint-disable banner — keep the header to a plain doc block.
const banner = [
  '/**',
  ' * AUTO-GENERATED -- DO NOT EDIT.',
  ' * Regenerate with `python scripts/codegen/generate.py` (issue #612).',
  ' * Source: schemas/metadata.schema.json',
  ' */',
].join('\n');

const schema = JSON.parse(await readFile(schemaPath, 'utf-8'));
const ts = await compile(schema, 'Metadata', {
  bannerComment: banner,
  declareExternallyReferenced: true,
  // Default (when schema doesn't specify) -- emit no `[k: string]: unknown`
  // index signature. The JSON Schema is the strict writer contract; the
  // reader-side passthrough that allows forward-compat with unknown fields
  // is provided by zod's `.passthrough()` (GUI) and Python's dict
  // (CLI), not by the generated TS interface (#612).
  additionalProperties: false,
  format: true,
  style: { singleQuote: true, semi: true, trailingComma: 'all' },
});

await writeFile(outPath, ts, 'utf-8');
console.log(`generated: ${outPath}`);
