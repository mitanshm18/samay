import type { KeyboardEvent } from "react";
import type { ThemePref } from "../theme";

const OPTIONS: { value: ThemePref; label: string; icon: string }[] = [
  { value: "light", label: "Light", icon: "M12 4V2M12 22v-2M4 12H2M22 12h-2M5.6 5.6 4.2 4.2M19.8 19.8l-1.4-1.4M5.6 18.4l-1.4 1.4M19.8 4.2l-1.4 1.4M12 8a4 4 0 100 8 4 4 0 000-8z" },
  { value: "dark", label: "Dark", icon: "M20 14.5A8 8 0 019.5 4a8 8 0 1010.5 10.5z" },
  { value: "system", label: "System", icon: "M3 5h18v11H3zM8 20h8M12 16v4" },
];

/** A radio group: arrow keys move the choice, as for any set of radio buttons. */
export function ThemeSwitcher({ pref, onChange }: { pref: ThemePref; onChange: (pref: ThemePref) => void }) {
  const onKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 0;
    if (!step) return;
    event.preventDefault();
    const index = OPTIONS.findIndex((o) => o.value === pref);
    const next = OPTIONS[(index + step + OPTIONS.length) % OPTIONS.length]!;
    onChange(next.value);
    (event.currentTarget.querySelector(`[data-value="${next.value}"]`) as HTMLElement | null)?.focus();
  };
  return (
    <div className="theme-switch" role="radiogroup" aria-label="Theme" onKeyDown={onKey}>
      {OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          data-value={option.value}
          aria-checked={pref === option.value}
          tabIndex={pref === option.value ? 0 : -1}
          className={pref === option.value ? "on" : ""}
          onClick={() => onChange(option.value)}
          title={`${option.label} theme`}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d={option.icon} />
          </svg>
          <span>{option.label}</span>
        </button>
      ))}
    </div>
  );
}
