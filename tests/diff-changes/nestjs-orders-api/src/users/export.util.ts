import { execSync } from 'child_process';

export async function exportUserCsv(userId: number, fileName: string): Promise<string> {
  const target = `/tmp/exports/${fileName}`;
  execSync(`psql -c "\\copy (SELECT * FROM \\"user\\" WHERE id = ${userId}) TO '${target}' CSV"`);
  return target;
}
