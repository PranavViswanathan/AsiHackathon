"use client";

type Props = {
  available: boolean;
  // master clock (epoch ms) and its range
  clockMs: number;
  minMs: number;
  maxMs: number;
  onClockChange: (ms: number) => void;
  playing: boolean;
  onPlayingChange: (v: boolean) => void;
  // layer toggles
  weatherAvailable: boolean;
  showWeather: boolean;
  onShowWeatherChange: (v: boolean) => void;
  aircraftAvailable: boolean;
  showAircraft: boolean;
  onShowAircraftChange: (v: boolean) => void;
  showPaths: boolean;
  onShowPathsChange: (v: boolean) => void;
};

// dBZ color legend matching src/web_animation.py
const DBZ_GRADIENT =
  "rgb(64,160,240),rgb(48,192,80),rgb(32,160,48),rgb(240,224,48),rgb(240,144,32),rgb(240,48,32),rgb(192,32,128)";

const TIME_FMT = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
  timeZone: "UTC",
});

function formatTime(ms: number): string {
  if (!Number.isFinite(ms)) return "--";
  return `${TIME_FMT.format(new Date(ms))} UTC`;
}

// Elapsed since the start of the window, e.g. "T+0:00", "T+2:15".
function formatOffset(ms: number, base: number): string {
  const mins = Math.round((ms - base) / 60000);
  if (!Number.isFinite(mins)) return "";
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return `T+${h}:${String(m).padStart(2, "0")}`;
}

function Toggle({
  label,
  on,
  disabled,
  onClick,
  activeClass,
}: {
  label: string;
  on: boolean;
  disabled: boolean;
  onClick: () => void;
  activeClass: string;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`px-3 py-1.5 text-sm font-medium rounded transition-colors shrink-0 ${
        disabled
          ? "bg-gray-800 text-gray-600 cursor-not-allowed"
          : on
          ? activeClass
          : "bg-gray-800 text-gray-300 hover:bg-gray-700"
      }`}
    >
      {label}
    </button>
  );
}

export default function TimelineControl({
  available,
  clockMs,
  minMs,
  maxMs,
  onClockChange,
  playing,
  onPlayingChange,
  weatherAvailable,
  showWeather,
  onShowWeatherChange,
  aircraftAvailable,
  showAircraft,
  onShowAircraftChange,
  showPaths,
  onShowPathsChange,
}: Props) {
  if (!available) return null;

  return (
    <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-20 w-[680px] max-w-[calc(100%-2rem)] bg-gray-900/90 backdrop-blur border border-gray-700 rounded-lg px-4 py-3 text-white shadow-xl">
      <div className="flex items-center gap-3">
        <Toggle
          label="Weather"
          on={showWeather}
          disabled={!weatherAvailable}
          onClick={() => onShowWeatherChange(!showWeather)}
          activeClass="bg-sky-600 text-white hover:bg-sky-500"
        />
        <Toggle
          label="Aircraft"
          on={showAircraft}
          disabled={!aircraftAvailable}
          onClick={() => onShowAircraftChange(!showAircraft)}
          activeClass="bg-amber-600 text-white hover:bg-amber-500"
        />
        <Toggle
          label="Paths"
          on={showPaths}
          disabled={!aircraftAvailable}
          onClick={() => onShowPathsChange(!showPaths)}
          activeClass="bg-emerald-600 text-white hover:bg-emerald-500"
        />

        <button
          onClick={() => onPlayingChange(!playing)}
          className="w-9 h-9 flex items-center justify-center rounded bg-gray-800 text-white hover:bg-gray-700 transition-colors shrink-0"
          title={playing ? "Pause" : "Play"}
        >
          <span className="text-sm">{playing ? "❚❚" : "▶"}</span>
        </button>

        <input
          type="range"
          min={minMs}
          max={maxMs}
          step={60000}
          value={clockMs}
          onChange={(e) => onClockChange(Number(e.target.value))}
          className="flex-1 accent-sky-500 cursor-pointer"
        />

        <div className="shrink-0 w-[140px] text-right">
          <div className="text-xs font-mono text-gray-100 tabular-nums">
            {formatTime(clockMs)}
          </div>
          <div className="text-[10px] font-mono text-sky-400 tabular-nums">
            {formatOffset(clockMs, minMs)}
          </div>
        </div>
      </div>

      {showWeather && (
        <div className="flex items-center gap-2 mt-2 pl-1">
          <span className="text-[10px] text-gray-400 uppercase tracking-wider shrink-0">
            Reflectivity
          </span>
          <div
            className="h-2 flex-1 rounded"
            style={{ background: `linear-gradient(to right, ${DBZ_GRADIENT})` }}
          />
          <div className="flex justify-between text-[10px] text-gray-400 shrink-0 gap-2">
            <span>light</span>
            <span>heavy</span>
            <span>severe</span>
          </div>
        </div>
      )}
    </div>
  );
}
