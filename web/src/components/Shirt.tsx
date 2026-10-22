import { useId } from "react";
import { kitFor } from "@/lib/clubs";

// A football shirt in club colours: body, sleeves with cuffs, V collar, soft shading.
export function Shirt({ team, goalkeeper, size = 64 }: { team: string; goalkeeper: boolean; size?: number }) {
  const kit = kitFor(team, goalkeeper);
  const id = useId().replace(/:/g, "");
  const body = kit.stripes ? `url(#stripes-${id})` : kit.body;
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" aria-hidden="true" className="drop-shadow-md">
      <defs>
        {kit.stripes && (
          <pattern id={`stripes-${id}`} width="16" height="100" patternUnits="userSpaceOnUse" x="2">
            <rect width="8" height="100" fill={kit.body} />
            <rect x="8" width="8" height="100" fill={kit.stripes} />
          </pattern>
        )}
        <linearGradient id={`shade-${id}`} x1="0" x2="1" y1="0" y2="0">
          <stop offset="0" stopColor="#000" stopOpacity="0.18" />
          <stop offset="0.35" stopColor="#fff" stopOpacity="0.10" />
          <stop offset="0.65" stopColor="#fff" stopOpacity="0" />
          <stop offset="1" stopColor="#000" stopOpacity="0.22" />
        </linearGradient>
      </defs>
      {/* sleeves */}
      <path d="M28 14 L8 28 L16 46 L30 38 Z" fill={kit.sleeves} stroke="#00000033" strokeWidth="1" />
      <path d="M72 14 L92 28 L84 46 L70 38 Z" fill={kit.sleeves} stroke="#00000033" strokeWidth="1" />
      <path d="M8 28 L16 46 L19 44.5 L11 27 Z" fill={kit.trim} opacity="0.9" />
      <path d="M92 28 L84 46 L81 44.5 L89 27 Z" fill={kit.trim} opacity="0.9" />
      {/* body */}
      <path
        d="M28 14 L40 9 Q50 17 60 9 L72 14 L70 38 L71 90 Q50 94 29 90 L30 38 Z"
        fill={body}
        stroke="#00000033"
        strokeWidth="1"
      />
      <path d="M28 14 L40 9 Q50 17 60 9 L72 14 L70 38 L71 90 Q50 94 29 90 L30 38 Z" fill={`url(#shade-${id})`} />
      {/* collar */}
      <path d="M40 9 Q50 17 60 9 L57 8 Q50 14 43 8 Z" fill={kit.trim} />
      <path d="M43 8 L50 20 L57 8" fill="none" stroke={kit.trim} strokeWidth="2.5" strokeLinejoin="round" />
    </svg>
  );
}
