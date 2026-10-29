import React from "react";

// Small stroke icons (24x24 viewBox) so the app has no icon-library dependency.
const PATHS = {
  overview: "M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z",
  map: "M9 4 3 6.5v13L9 17l6 3 6-2.5v-13L15 7 9 4zm0 0v13m6-10v13",
  robot: "M12 3v3m-7 5h14a1 1 0 0 1 1 1v6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-6a1 1 0 0 1 1-1zm4 3v1m6-1v1M2 14v2m20-2v2",
  dispatch: "M4 6h16M4 12h10M4 18h16m3-6-3-3m3 3-3 3",
  chart: "M4 20V10m6 10V4m6 16v-7m5 7H3",
  package: "M12 3 3 7.5v9L12 21l9-4.5v-9L12 3zm0 9 9-4.5M12 12v9M12 12 3 7.5M7.5 5.2l9 4.6",
  target: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zm0-5a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm0-3a1 1 0 1 0 0-2 1 1 0 0 0 0 2z",
  battery: "M3 8h15a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1zm17 2.5h1.5v3H20",
  check: "m5 12 5 5 9-10",
  clock: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zm0-14v5l3 2",
  alert: "M12 3 2 20h20L12 3zm0 6v5m0 3v.01",
  bolt: "M13 2 4 14h7l-1 8 9-12h-7l1-8z",
  reset: "M4 4v6h6M20 20v-6h-6M5.6 15A8 8 0 0 0 20 12M18.4 9A8 8 0 0 0 4 12",
  play: "M7 4v16l13-8L7 4z",
  pause: "M8 5v14m8-14v14",
  step: "M5 4v16l10-8L5 4zm13 0v16",
  plus: "M12 5v14M5 12h14",
  send: "M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z",
  info: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zm0-11v6m0-9v.01",
  x: "M6 6l12 12M18 6 6 18",
  pin: "M12 21s7-6.2 7-12a7 7 0 1 0-14 0c0 5.8 7 12 7 12zm0-9a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
};

export default function Icon({ name, size = 18, className = "", strokeWidth = 1.8 }) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={PATHS[name] || PATHS.info} />
    </svg>
  );
}
