import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

// Ported from sampai/frontend/src/lib/utils.ts.
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
