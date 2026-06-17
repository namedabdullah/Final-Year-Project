// One-off: convert the web app's OKLCH design tokens (sampai/frontend/src/index.css)
// to sRGB "R G B" channels for the NativeWind v4 `rgb(var(--x) / <alpha-value>)` pattern.
// Run: node scripts/_gen-theme.cjs
function oklchToRgb(L, C, H) {
  const h = (H * Math.PI) / 180;
  const a = C * Math.cos(h);
  const b = C * Math.sin(h);
  const l_ = L + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = L - 0.0894841775 * a - 1.291485548 * b;
  const l = l_ ** 3, m = m_ ** 3, s = s_ ** 3;
  let r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s;
  let g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s;
  let bl = -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s;
  const enc = (c) => {
    c = c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(c, 1 / 2.4) - 0.055;
    return Math.max(0, Math.min(255, Math.round(c * 255)));
  };
  return `${enc(r)} ${enc(g)} ${enc(bl)}`;
}
const light = {
  background: [0.99, 0.005, 240], foreground: [0.15, 0.01, 240],
  card: [1, 0, 0], 'card-foreground': [0.15, 0.01, 240],
  popover: [1, 0, 0], 'popover-foreground': [0.15, 0.01, 240],
  primary: [0.25, 0.02, 240], 'primary-foreground': [0.99, 0.005, 240],
  secondary: [0.96, 0.01, 240], 'secondary-foreground': [0.25, 0.02, 240],
  muted: [0.96, 0.01, 240], 'muted-foreground': [0.55, 0.015, 240],
  accent: [0.96, 0.01, 240], 'accent-foreground': [0.25, 0.02, 240],
  destructive: [0.577, 0.245, 27.325], 'destructive-foreground': [0.99, 0.005, 240],
  border: [0.92, 0.01, 240], input: [0.92, 0.01, 240], ring: [0.55, 0.15, 260],
  'chart-1': [0.55, 0.22, 260], 'chart-2': [0.6, 0.2, 220], 'chart-3': [0.5, 0.18, 280],
  'chart-4': [0.65, 0.2, 200], 'chart-5': [0.7, 0.18, 240],
};
const dark = {
  background: [0.12, 0.02, 240], foreground: [0.98, 0.005, 240],
  card: [0.15, 0.02, 240], 'card-foreground': [0.98, 0.005, 240],
  popover: [0.15, 0.02, 240], 'popover-foreground': [0.98, 0.005, 240],
  primary: [0.98, 0.005, 240], 'primary-foreground': [0.15, 0.02, 240],
  secondary: [0.22, 0.025, 240], 'secondary-foreground': [0.98, 0.005, 240],
  muted: [0.22, 0.025, 240], 'muted-foreground': [0.65, 0.02, 240],
  accent: [0.22, 0.025, 240], 'accent-foreground': [0.98, 0.005, 240],
  destructive: [0.45, 0.18, 25], 'destructive-foreground': [0.98, 0.005, 240],
  border: [0.25, 0.025, 240], input: [0.25, 0.025, 240], ring: [0.55, 0.2, 260],
  'chart-1': [0.6, 0.25, 260], 'chart-2': [0.65, 0.22, 220], 'chart-3': [0.55, 0.2, 280],
  'chart-4': [0.7, 0.23, 200], 'chart-5': [0.75, 0.2, 240],
};
const emit = (obj) => Object.entries(obj).map(([k, v]) => `    --${k}: ${oklchToRgb(...v)};`).join('\n');
console.log(':root {\n' + emit(light) + '\n  }');
console.log('.dark:root {\n' + emit(dark) + '\n  }');
