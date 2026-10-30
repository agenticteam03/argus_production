// T-0016: the side panel's icons, drawn like ui.jsx's (24-unit stroke icons in currentColor), kept here so the panel
// does not touch the shared file other console pull requests edit.
const icon = (paths) => (props) => (
  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"
    strokeLinejoin="round" aria-hidden="true" {...props}>{paths}</svg>
);

export const TerminalIcon = icon(<><rect width="20" height="16" x="2" y="4" rx="2" /><path d="m6 9 3 3-3 3M12 15h6" /></>);
export const KeyIcon = icon(<><circle cx="7.5" cy="15.5" r="4.5" /><path d="m10.7 12.3 9.3-9.3M17 6l3 3M14 9l2 2" /></>);
export const Maximize = icon(<path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />);
export const Minimize = icon(<path d="M4 14h6v6M20 10h-6V4M14 10l7-7M3 21l7-7" />);
export const Minus = icon(<path d="M5 12h14" />);
export const Plus = icon(<path d="M12 5v14M5 12h14" />);
export const Power = icon(<><path d="M12 2v10" /><path d="M18.4 6.6a9 9 0 1 1-12.8 0" /></>);
export const PanelIcon = icon(<><rect width="18" height="18" x="3" y="3" rx="2" /><path d="M3 15h18" /></>);
