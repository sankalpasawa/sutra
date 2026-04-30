import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseManifest, validateManifest } from '../../lib/manifest.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const manifestsDir = resolve(__dirname, '..', '..', 'manifests');

const SHIPPED = ['slack', 'gmail'];

describe('shipped manifests parse + validate cleanly', () => {
  for (const name of SHIPPED) {
    it(`${name}.yaml — parseManifest accepts the shipped manifest`, () => {
      const text = readFileSync(resolve(manifestsDir, `${name}.yaml`), 'utf8');
      const manifest = parseManifest(text);
      expect(manifest.schemaVersion).toBe('1');
      expect(manifest.name).toBe(name);
      expect(manifest.capabilities.length).toBeGreaterThan(0);
      expect(Object.keys(manifest.tierAccess)).toEqual(
        expect.arrayContaining(['T1', 'T2', 'T3', 'T4']),
      );
    });

    it(`${name}.yaml — validateManifest accepts (no overbroad capabilities, no missing fields)`, () => {
      const text = readFileSync(resolve(manifestsDir, `${name}.yaml`), 'utf8');
      const manifest = parseManifest(text);
      expect(() => validateManifest(manifest)).not.toThrow();
    });

    it(`${name}.yaml — every redactPath has no leading 'response.' (post-iter-11 P1#2 fix)`, () => {
      const text = readFileSync(resolve(manifestsDir, `${name}.yaml`), 'utf8');
      const manifest = parseManifest(text);
      for (const path of manifest.redactPaths) {
        expect(path.startsWith('response.')).toBe(false);
      }
    });
  }
});
