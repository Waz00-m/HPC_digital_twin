import { readFile, writeFile, mkdir, rename } from 'node:fs/promises';
import { dirname } from 'node:path';
import { randomUUID } from 'node:crypto';
import { validateScenario } from './engine.mjs';
export function createScenarioStore(path) {
  let queue = Promise.resolve();
  async function list() {
    try { return JSON.parse(await readFile(path, 'utf8')); }
    catch (error) { if (error.code === 'ENOENT') return []; throw error; }
  }
  function save(input) {
    const scenario = validateScenario(input);
    const job = queue.then(async () => {
      const drafts = await list();
      if (drafts.length >= 100) throw new Error('The local scenario library is limited to 100 drafts.');
      const draft = { id: randomUUID(), createdAt: new Date().toISOString(), config: scenario };
      drafts.push(draft); await mkdir(dirname(path), { recursive: true });
      await writeFile(path + '.tmp', JSON.stringify(drafts, null, 2) + '\n'); await rename(path + '.tmp', path);
      return draft;
    });
    queue = job.catch(() => {}); return job;
  }
  return { list, save };
}
