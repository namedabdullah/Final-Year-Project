// Mirrors the web signup rules in sampai/frontend/src/components/auth/auth-card.tsx
// and the backend constraints (username 3–50; password >=8 with letter + number).
export const USERNAME_RE = /^[a-zA-Z0-9_-]{3,50}$/;
export const EMAIL_RE = /\S+@\S+\.\S+/;

export const usernameValid = (u: string): boolean => USERNAME_RE.test(u);
export const emailValid = (e: string): boolean => EMAIL_RE.test(e);

export function passwordChecks(pw: string) {
  return {
    length: pw.length >= 8,
    letter: /[A-Za-z]/.test(pw),
    number: /\d/.test(pw),
  };
}

export function passwordValid(pw: string): boolean {
  const c = passwordChecks(pw);
  return c.length && c.letter && c.number;
}
