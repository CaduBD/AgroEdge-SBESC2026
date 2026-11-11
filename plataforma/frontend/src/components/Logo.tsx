import { cn } from "@/lib/utils";

export function MarcaLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={cn("size-8 shrink-0", className)}>
      <rect width="32" height="32" rx="9" className="fill-primary" />
      <path
        d="M16 7c-4 5-6 8.4-6 11a6 6 0 0 0 12 0c0-2.6-2-6-6-11Z"
        className="fill-primary-foreground"
      />
      <path
        d="M16 25v-7m0 3 3-3"
        className="stroke-primary"
        strokeWidth="1.6"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  );
}

export function Logo({ className, compacto = false }: { className?: string; compacto?: boolean }) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <MarcaLogo />
      {!compacto && (
        <span className="font-display text-lg font-semibold tracking-tight">
          Agro<span className="text-primary">Edge</span>
        </span>
      )}
    </div>
  );
}
