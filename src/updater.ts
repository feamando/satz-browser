import { getVersion } from "@tauri-apps/api/app";
import { invoke } from "@tauri-apps/api/core";
import { relaunch } from "@tauri-apps/plugin-process";
import { check, type Update } from "@tauri-apps/plugin-updater";

let cachedPendingUpdate: Update | null = null;

export async function getInstalledAppVersion(): Promise<string> {
  try {
    return await getVersion();
  } catch {
    return "0.5.0";
  }
}

export async function checkForAppUpdate(): Promise<{
  currentVersion: string;
  availableVersion: string | null;
  notes: string;
  error?: string;
}> {
  const currentVersion = await getInstalledAppVersion();
  try {
    const update = await check();
    if (update) {
      cachedPendingUpdate = update;
      return {
        currentVersion: update.currentVersion || currentVersion,
        availableVersion: update.version,
        notes: update.body ?? "",
      };
    }
    cachedPendingUpdate = null;
    return {
      currentVersion,
      availableVersion: null,
      notes: "",
    };
  } catch (err) {
    return {
      currentVersion,
      availableVersion: null,
      notes: "",
      error: err instanceof Error ? err.message : String(err),
    };
  }
}

export async function downloadAndInstallAppUpdate(
  onProgress: (pct: number) => void
): Promise<{ ok: boolean; error?: string }> {
  try {
    const update = cachedPendingUpdate ?? (await check());
    if (!update) {
      return { ok: false, error: "No update available." };
    }
    cachedPendingUpdate = update;

    let downloaded = 0;
    let total = 0;

    // Finish downloading before stopping the sidecar and running install() so
    // background Python processes never hold file locks on Windows installers.
    await update.download((ev) => {
      if (ev.event === "Started") {
        total = Number(ev.data.contentLength ?? 0);
        onProgress(0);
      } else if (ev.event === "Progress") {
        downloaded += Number(ev.data.chunkLength ?? 0);
        if (total > 0) {
          onProgress(Math.min(99, Math.round((100 * downloaded) / total)));
        }
      } else if (ev.event === "Finished") {
        onProgress(100);
      }
    });

    onProgress(100);
    try {
      await invoke("prepare_for_update");
    } catch {
      // Non-fatal if sidecar is already stopped
    }

    await update.install();
    await relaunch();
    return { ok: true };
  } catch (err) {
    return {
      ok: false,
      error: err instanceof Error ? err.message : String(err),
    };
  }
}
