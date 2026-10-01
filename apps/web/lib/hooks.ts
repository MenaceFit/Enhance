"use client";

import useSWR from "swr";
import { fetcher } from "./api";
import type { Dashboard, Me, PhotoDetail, PhotoSummary, Project } from "./types";

export function useMe() {
  return useSWR<Me>("/auth/me", fetcher, { revalidateOnFocus: true });
}

export function useDashboard(enabled = true) {
  return useSWR<Dashboard>(enabled ? "/dashboard" : null, fetcher);
}

const busy = (status?: string) => status === "queued" || status === "processing";

export function usePhoto(id: string) {
  return useSWR<PhotoDetail>(`/photos/${id}`, fetcher, {
    refreshInterval: (data) => (busy(data?.status) ? 800 : 0),
  });
}

export function useProject(id: string) {
  return useSWR<Project>(`/projects/${id}`, fetcher, {
    refreshInterval: (data) =>
      data && (data.photos?.some((p) => busy(p.status)) || (data.active_jobs?.length ?? 0) > 0) ? 900 : 0,
  });
}

export function useProjects(enabled = true) {
  return useSWR<{ projects: Project[] }>(enabled ? "/projects" : null, fetcher);
}

export function usePhotos(favorites = false, enabled = true) {
  return useSWR<{ photos: PhotoSummary[]; total: number }>(
    enabled ? `/photos?favorites=${favorites}&limit=120` : null,
    fetcher,
    { refreshInterval: (data) => (data?.photos.some((p) => busy(p.status)) ? 1200 : 0) },
  );
}
