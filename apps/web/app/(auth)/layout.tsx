/* eslint-disable @next/next/no-img-element */
import { Logo } from "@/components/logo";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="flex flex-col px-4 py-6 sm:px-10">
        <Logo />
        <div className="flex flex-1 items-center justify-center py-12">
          <div className="w-full max-w-sm animate-fade-up">{children}</div>
        </div>
      </div>
      <div className="relative hidden overflow-hidden bg-mist lg:block">
        <img src="/demo/veste-after.webp" alt="" className="absolute inset-0 size-full object-cover" />
        <div className="absolute inset-x-8 bottom-8 rounded-2xl bg-paper/90 p-6 backdrop-blur">
          <p className="text-lg font-semibold tracking-tight">« Améliorer la présentation, jamais falsifier l&apos;article. »</p>
          <p className="mt-2 text-sm text-muted">Fidélité couleur mesurée · imperfections signalées · photos privées</p>
        </div>
      </div>
    </div>
  );
}
