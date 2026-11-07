// Node 25 and later ship their own experimental `localStorage` global, which hides
// jsdom's and is undefined unless Node is started with --localstorage-file. Give the
// tests a plain in-memory Storage in that case, so they behave the same on every Node.

function memoryStorage(): Storage {
  const items = new Map<string, string>();
  return {
    get length() {
      return items.size;
    },
    clear: () => items.clear(),
    getItem: (key: string) => items.get(key) ?? null,
    key: (index: number) => [...items.keys()][index] ?? null,
    removeItem: (key: string) => void items.delete(key),
    setItem: (key: string, value: string) => void items.set(key, String(value)),
  };
}

function usable(): boolean {
  try {
    return typeof window.localStorage?.clear === "function";
  } catch {
    return false;
  }
}

if (typeof window !== "undefined" && !usable()) {
  const storage = memoryStorage();
  Object.defineProperty(window, "localStorage", { configurable: true, get: () => storage });
  Object.defineProperty(globalThis, "localStorage", { configurable: true, get: () => storage });
}
