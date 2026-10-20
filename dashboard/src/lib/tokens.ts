/** Design tokens — fintech terminal */

export const colors = {
  base: "#0B0F14",
  panel: "#11161D",
  border: "#1E2630",
  text: "#E1E4E8",
  textMuted: "#8B949E",
  usdcBlue: "#2775CA",
  baseBlue: "#0052FF",
  amber: "#F5A623",
  green: "#2FBF71",
  red: "#E5484D",
  white: "#FFFFFF",
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
} as const;

export const radius = {
  sm: 6,
  md: 10,
  lg: 16,
} as const;

export const fonts = {
  ui: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
  mono: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
} as const;

export const transition = "150ms ease-out";
