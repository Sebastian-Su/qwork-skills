import { createRequire } from "node:module";
import path from "node:path";

// The Skill entity is external to QWork. Bind third-party packages to the
// invoking repository instead of relying on this file's physical ancestors.
export const requireFromProject = createRequire(path.join(process.cwd(), "package.json"));
