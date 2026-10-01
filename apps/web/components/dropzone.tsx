"use client";

import { ImagePlus, Upload } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { useSWRConfig } from "swr";
import { uploadPhotos } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ProgressBar } from "./ui/controls";
import { useToast } from "./ui/toast";

const ACCEPT = ["image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"];
const EXT = /\.(jpe?g|png|webp|heic|heif)$/i;
const MAX_FILES = 12;
const MAX_MB = 25;

/**
 * Drag & drop, click to pick, paste (Ctrl/Cmd+V) and multiple files.
 * After upload: one photo → editor, several → the listing (project) page.
 */
export function Dropzone({
  projectId,
  compact = false,
  onUploaded,
  className,
}: {
  projectId?: string;
  compact?: boolean;
  onUploaded?: (projectId: string, photoIds: string[]) => void;
  className?: string;
}) {
  const router = useRouter();
  const toast = useToast();
  const { mutate } = useSWRConfig();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);

  const send = useCallback(
    async (list: File[]) => {
      const files = list.filter((f) => ACCEPT.includes(f.type) || EXT.test(f.name));
      if (!files.length) {
        toast("Formats acceptés : JPG, PNG, WEBP ou HEIC.", "error");
        return;
      }
      if (files.length > MAX_FILES) {
        toast(`Maximum ${MAX_FILES} photos à la fois.`, "error");
        return;
      }
      const tooBig = files.find((f) => f.size > MAX_MB * 1024 * 1024);
      if (tooBig) {
        toast(`${tooBig.name} dépasse ${MAX_MB} Mo.`, "error");
        return;
      }
      setProgress(0);
      try {
        const res = await uploadPhotos(files, { projectId, onProgress: setProgress });
        mutate("/auth/me");
        mutate("/dashboard");
        const ids = res.photos.map((p) => p.id);
        if (onUploaded) onUploaded(res.project.id, ids);
        else if (ids.length === 1) router.push(`/app/photos/${ids[0]}`);
        else router.push(`/app/projects/${res.project.id}`);
      } catch (e) {
        toast((e as Error).message, "error");
        if ((e as { status?: number }).status === 402) router.push("/app/billing?reason=credits");
      } finally {
        setProgress(null);
      }
    },
    [mutate, onUploaded, projectId, router, toast],
  );

  // paste anywhere on the page
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const files = Array.from(e.clipboardData?.files ?? []);
      if (files.length) {
        e.preventDefault();
        void send(files);
      }
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [send]);

  const uploading = progress !== null;

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        void send(Array.from(e.dataTransfer.files));
      }}
      className={cn(
        "relative flex flex-col items-center justify-center rounded-2xl border border-dashed text-center transition-all duration-300",
        over ? "scale-[1.01] border-ink bg-mist" : "border-line-strong bg-paper hover:border-graphite",
        compact ? "gap-2 px-6 py-8" : "gap-4 px-6 py-16 sm:py-20",
        className,
      )}
    >
      <input
        ref={input}
        type="file"
        multiple
        accept={[...ACCEPT, ".heic", ".heif"].join(",")}
        className="hidden"
        onChange={(e) => {
          void send(Array.from(e.target.files ?? []));
          e.target.value = "";
        }}
      />
      {uploading ? (
        <div className="w-full max-w-xs space-y-3">
          <Upload className="mx-auto size-6 animate-pulse-soft" />
          <p className="text-sm font-medium">Envoi de tes photos…</p>
          <ProgressBar value={progress ?? 0} />
        </div>
      ) : (
        <>
          <div className={cn("flex items-center justify-center rounded-full bg-mist", compact ? "size-11" : "size-14")}>
            <ImagePlus className={compact ? "size-5" : "size-6"} strokeWidth={1.6} />
          </div>
          <div>
            <p className={cn("font-semibold tracking-tight", compact ? "text-base" : "text-xl")}>📸 Dépose ta photo ici</p>
            <p className="mt-1 text-sm text-muted">
              ou{" "}
              <button type="button" onClick={() => input.current?.click()} className="font-medium text-ink underline underline-offset-4">
                choisis-la sur ton appareil
              </button>
              {!compact && <> · colle-la avec ⌘V</>}
            </p>
          </div>
          {!compact && (
            <p className="text-xs text-subtle">JPG, PNG, WEBP, HEIC · jusqu&apos;à {MAX_FILES} photos · {MAX_MB} Mo max par photo</p>
          )}
          <button type="button" aria-label="Choisir des photos" className="absolute inset-0 -z-0 cursor-pointer" onClick={() => input.current?.click()} tabIndex={-1} />
        </>
      )}
    </div>
  );
}
