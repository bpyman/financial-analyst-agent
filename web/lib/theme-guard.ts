/** The theme values next-themes stores; anything else is a corrupt entry. */
export const THEMES = ["light", "dark", "system"] as const;

/**
 * Runs before next-themes' own script. next-themes writes whatever it finds in
 * localStorage into <html class>, so a corrupt value is dropped first and the
 * default theme applies.
 */
export const THEME_GUARD_SCRIPT = `try{var t=localStorage.getItem("theme");if(t!==null&&${JSON.stringify(
  THEMES,
)}.indexOf(t)<0)localStorage.removeItem("theme")}catch(e){}`;
