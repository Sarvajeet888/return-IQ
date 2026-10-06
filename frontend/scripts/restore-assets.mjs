import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const publicDir = join(here, '..', 'public');
for (const name of ['scroll_video.mp4', 'truck_video.mp4']) {
  const target = join(publicDir, name);
  if (existsSync(target)) continue;
  const encoded = readFileSync(`${target}.b64`, 'utf8').trim();
  writeFileSync(target, Buffer.from(encoded, 'base64'));
  console.log(`restored ${name}`);
}
