import { getApps, initializeApp } from 'firebase-admin/app';
import { getAuth } from 'firebase-admin/auth';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

if (!getApps().length) {
  const configPath = path.resolve(__dirname, '../../firebase-applet-config.json');
  let projectId: string | undefined;
  if (fs.existsSync(configPath)) {
    try {
      const config = JSON.parse(fs.readFileSync(configPath, 'utf-8'));
      projectId = config.projectId;
    } catch {
      // ignore parse error
    }
  }

  initializeApp(projectId ? { projectId } : {});
}

export const adminAuth = getAuth();

