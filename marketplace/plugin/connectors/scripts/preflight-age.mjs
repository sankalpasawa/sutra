/**
 * Preflight: assert `age` CLI is available in PATH.
 *
 * Used by call.mjs, verify-connection.mjs, save-credential.mjs as defense-
 * in-depth (bin/sutra runs the same check before dispatching, but these
 * scripts can also be invoked directly via `node scripts/<x>.mjs`).
 *
 * Fails loudly with install instructions; exits 1 if missing.
 */
import { spawnSync } from "node:child_process";

export function assertAgeAvailable() {
  const result = spawnSync("age", ["--version"], { stdio: "ignore" });
  if (result.error || result.status !== 0) {
    process.stderr.write(
      "Sutra Connectors require the 'age' CLI for credential encryption.\n\n" +
        "Install:\n" +
        "  brew install age          # macOS\n" +
        "  apt install age           # Debian/Ubuntu\n" +
        "  pacman -S age             # Arch\n" +
        "  scoop install age         # Windows (scoop)\n\n" +
        "Or download: https://github.com/FiloSottile/age/releases\n\n" +
        "Then re-run.\n"
    );
    process.exit(1);
  }
}
