import { useCallback, useState } from "react";
import { otherTheme, readTheme, saveTheme, switchTheme } from "../utils/theme.js";

// The current theme and a toggle. The initial value is what main.jsx already applied to <html> before the first render.
export function useTheme() {
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme ?? readTheme());
  const toggle = useCallback(() => {
    const next = otherTheme(theme);
    switchTheme(next);
    saveTheme(next);
    setTheme(next);
  }, [theme]);
  return [theme, toggle];
}
