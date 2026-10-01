import type { Job } from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

const BASE = "/api/v1";

async function parse(res: Response) {
  if (res.status === 204) return null;
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const detail = data?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? "Certaines informations sont invalides."
          : "Une erreur est survenue. Réessaie dans un instant.";
    throw new ApiError(res.status, message);
  }
  return data;
}

export async function api<T = unknown>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  const res = await fetch(`${BASE}${path}`, {
    credentials: "same-origin",
    ...rest,
    headers: {
      ...(json !== undefined ? { "Content-Type": "application/json" } : {}),
      "X-Requested-With": "fetch",
      ...headers,
    },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
  return parse(res) as Promise<T>;
}

export const fetcher = <T,>(path: string) => api<T>(path);

/** Upload with real progress (fetch has no upload progress events). */
export function uploadPhotos(
  files: File[],
  opts: { projectId?: string; onProgress?: (fraction: number) => void } = {},
): Promise<{ project: { id: string }; photos: { id: string }[]; jobs: Job[] }> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f, f.name || "photo.jpg"));
    if (opts.projectId) form.append("project_id", opts.projectId);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${BASE}/uploads`);
    xhr.withCredentials = true;
    xhr.setRequestHeader("X-Requested-With", "fetch");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) opts.onProgress?.(e.loaded / e.total);
    };
    xhr.onload = () => {
      let data: { detail?: string } | null = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        /* ignore */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data as never);
      else reject(new ApiError(xhr.status, typeof data?.detail === "string" ? data.detail : "L'envoi a échoué."));
    };
    xhr.onerror = () => reject(new ApiError(0, "Connexion perdue pendant l'envoi."));
    xhr.send(form);
  });
}

export async function waitForJob(id: string, onUpdate?: (job: Job) => void, intervalMs = 700): Promise<Job> {
  for (;;) {
    const job = await api<Job>(`/jobs/${id}`);
    onUpdate?.(job);
    if (job.status === "succeeded") return job;
    if (job.status === "failed") throw new ApiError(500, job.error ?? "Le traitement a échoué.");
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}
