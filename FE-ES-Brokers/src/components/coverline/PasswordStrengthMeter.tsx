function scorePassword(password: string): number {
  if (!password) return 0;
  let score = 0;
  if (password.length >= 8) score++;
  if (password.length >= 12) score++;
  if (/[A-Z]/.test(password) && /[a-z]/.test(password)) score++;
  if (/\d/.test(password)) score++;
  if (/[^A-Za-z0-9]/.test(password)) score++;
  return Math.min(score, 4);
}

const LABELS = ["Too short", "Weak", "Fair", "Good", "Strong"];
const COLORS = ["bg-destructive", "bg-destructive", "bg-warn", "bg-accent-2", "bg-success"];

export function PasswordStrengthMeter({ password }: { password: string }) {
  const score = scorePassword(password);
  return (
    <div aria-live="polite" className="mt-1.5">
      <div className="flex gap-1">
        {[0, 1, 2, 3].map((i) => (
          <div
            key={i}
            className={`h-1 flex-1 rounded-full transition-colors duration-300 ${
              password && i < score ? COLORS[score] : "bg-secondary"
            }`}
          />
        ))}
      </div>
      {password && <div className="mt-1 text-[11px] text-muted-foreground">{LABELS[score]}</div>}
    </div>
  );
}
