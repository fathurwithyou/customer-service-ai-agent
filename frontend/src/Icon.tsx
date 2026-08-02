/** One inline set, so the UI has no icon dependency and no network request for a 16px glyph.
 *  The name arrives from the backend beside the label -- see `shared/activity.py`. */
const PATHS: Record<string, string> = {
  user: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8M4 20c0-3.3 3.6-5 8-5s8 1.7 8 5",
  list: "M8 6h12M8 12h12M8 18h12M3.5 6h.01M3.5 12h.01M3.5 18h.01",
  box: "M12 3 3.5 7.5v9L12 21l8.5-4.5v-9zM3.5 7.5 12 12m0 9v-9m8.5-4.5L12 12",
  truck: "M3 7h10v9H3zM13 11h4l3 3v2h-7zM7 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4m10 0a2 2 0 1 0 0-4 2 2 0 0 0 0 4",
  pin: "M12 21s7-6 7-11a7 7 0 1 0-14 0c0 5 7 11 7 11m0-8a3 3 0 1 0 0-6 3 3 0 0 0 0 6",
  tag: "M3 12V4h8l9 9-8 8zM7.5 7.5h.01",
  undo: "M4 10h9a5 5 0 0 1 0 10H8M4 10l4-4M4 10l4 4",
  note: "M6 3h9l4 4v14H6zM14 3v5h5M9 13h7M9 17h5",
  headset: "M4 15v-3a8 8 0 0 1 16 0v3M4 15a2 2 0 0 0 2 2h1v-5H6a2 2 0 0 0-2 2m16 0a2 2 0 0 1-2 2h-1v-5h1a2 2 0 0 1 2 2m-3 4v1a2 2 0 0 1-2 2h-3",
  dot: "M12 12h.01",
  check: "M4.5 12.5 9.5 17.5 19.5 7",
  trash: "M4 7h16M9 7V5h6v2M6.5 7l.8 13h9.4l.8-13M10 11v6M14 11v6",
  plus: "M12 5v14M5 12h14",
  spark: "M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18",
};

export function Icon({ name }: { name: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"
         strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={PATHS[name] ?? PATHS.dot} />
    </svg>
  );
}
