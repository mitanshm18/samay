// The repository's synthetic example bills (examples/bills), offered as one-click
// samples. golden-gb* are the three bills checked by hand (tests/golden). They are
// bundled as text, exactly as in the files.

const files = import.meta.glob<string>("../../examples/bills/*.json", {
  query: "?raw",
  import: "default",
  eager: true,
});

const DESCRIPTIONS: Record<string, string> = {
  matching: "Every printed line matches",
  differing: "One printed line is 1 paisa off",
  "missing-data": "ToD readings missing; ToD line illegible",
  "pass-through": "Meter rent taken as printed; an estimated reading",
  "golden-gb1": "Hand-checked GB1: excess demand line not on the printed bill",
  "golden-gb2": "Hand-checked GB2: energy printed 1 paisa high; meter rent",
  "golden-gb3": "Hand-checked GB3: ToD illegible; duty and rounding not printed",
};

export type Example = { name: string; description: string; text: string };

export const EXAMPLES: Example[] = Object.entries(files)
  .map(([path, text]) => {
    const name = path.split("/").pop()?.replace(/\.json$/, "") ?? path;
    return { name, description: DESCRIPTIONS[name] ?? "", text };
  })
  .sort((a, b) => a.name.localeCompare(b.name));
