import { ReactNode, useState } from "react";
import { NewSystemSettings, SystemSettings } from "../api/client";
import { Button } from "../components/Button";
import { EmptyState } from "../components/EmptyState";
import { LoadingCards } from "../components/LoadingCards";
import { SystemStatus } from "../components/SystemStatus";
import { AlertIcon, CheckIcon, SpinnerIcon } from "../components/icons";
import { StatusController } from "../hooks/useStatus";
import { useSettings } from "../hooks/useSettings";

interface FieldProps {
  label: string;
  name: string;
  defaultValue?: string | number | null;
  type?: string;
  required?: boolean;
  hint?: string;
  min?: number;
  max?: number;
  step?: string;
  placeholder?: string;
  readOnly?: boolean;
}

function Field({
  label,
  name,
  defaultValue,
  type = "text",
  required,
  hint,
  min,
  max,
  step,
  placeholder,
  readOnly,
}: FieldProps) {
  const hintId = hint ? `${name}-hint` : undefined;
  return (
    <div className="flex flex-col gap-1.5">
      <label
        htmlFor={name}
        className="text-xs uppercase tracking-wider text-gray-400"
      >
        {label}
        {required && <span className="ml-1 text-solar-400">required</span>}
      </label>
      <input
        id={name}
        name={name}
        type={type}
        defaultValue={defaultValue ?? ""}
        required={required}
        min={min}
        max={max}
        step={step}
        placeholder={placeholder}
        readOnly={readOnly}
        aria-describedby={hintId}
        className={
          readOnly
            ? "cursor-not-allowed rounded-lg border border-gray-800 bg-gray-900/60 px-3 py-2 text-sm text-gray-400"
            : "rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-white placeholder:text-gray-500 focus:border-solar-500 focus:outline-none focus:ring-1 focus:ring-solar-500"
        }
      />
      {hint && (
        <p id={hintId} className="text-xs leading-relaxed text-gray-400">
          {hint}
        </p>
      )}
    </div>
  );
}

function Group({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <fieldset className="mt-10 first:mt-0">
      <legend className="text-sm font-semibold text-white">{title}</legend>
      <p className="mt-1.5 max-w-prose text-sm leading-relaxed text-gray-400">
        {description}
      </p>
      <div className="mt-5 grid grid-cols-1 gap-5 sm:grid-cols-2">
        {children}
      </div>
    </fieldset>
  );
}

function trimmed(form: FormData, key: string): string | null {
  const value = form.get(key);
  const text = typeof value === "string" ? value.trim() : "";
  return text === "" ? null : text;
}

function numeric(form: FormData, key: string): number | null {
  const text = trimmed(form, key);
  return text === null ? null : Number(text);
}

function withoutNulls<T extends object>(payload: T): T {
  return Object.fromEntries(
    Object.entries(payload).filter(([, value]) => value !== null)
  ) as T;
}

interface SetupPageProps {
  status: StatusController;
}

export function SetupPage({ status }: SetupPageProps) {
  const { data, loading, error, save, create } = useSettings();
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [justCreated, setJustCreated] = useState(false);

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-white">Setup</h1>
        <LoadingCards count={2} label="Loading system settings" />
      </div>
    );
  }

  if (error) {
    return (
      <EmptyState
        icon={<AlertIcon />}
        title="Could not load your settings"
        tone="alert"
        action={
          <Button variant="secondary" onClick={() => window.location.reload()}>
            Reload
          </Button>
        }
      >
        <p>{error}</p>
      </EmptyState>
    );
  }

  const isNew = data === null;

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setSaving(true);
    setSaveError(null);
    try {
      const shared = {
        location: (form.get("location") as string).trim(),
        system_size_kw: trimmed(form, "system_size_kw"),
        panel_count: numeric(form, "panel_count"),
        panel_wattage_w: numeric(form, "panel_wattage_w"),
        tilt_angle_deg: trimmed(form, "tilt_angle_deg"),
        azimuth_deg: trimmed(form, "azimuth_deg"),
        degradation_rate: trimmed(form, "degradation_rate"),
      };
      if (isNew) {
        await create(
          withoutNulls({
            enphase_system_id: trimmed(form, "enphase_system_id") ?? "",
            install_date: trimmed(form, "install_date") ?? "",
            latitude: trimmed(form, "latitude") ?? "",
            longitude: trimmed(form, "longitude") ?? "",
            name: (form.get("name") as string).trim(),
            ...shared,
          }) as NewSystemSettings
        );
        setJustCreated(true);
      } else {
        await save(
          withoutNulls({
            name: (form.get("name") as string).trim(),
            install_date: trimmed(form, "install_date"),
            latitude: trimmed(form, "latitude"),
            longitude: trimmed(form, "longitude"),
            ...shared,
          }) as Partial<SystemSettings>
        );
      }
      await status.refresh();
    } catch (err) {
      setSaveError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  const effectiveSource = status.data?.irradiance_source ?? "nrel";

  return (
    <div className="max-w-2xl space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-white">
          {isNew ? "Set up your system" : "System settings"}
        </h1>
        {isNew && (
          <p className="mt-3 max-w-prose text-sm leading-relaxed text-gray-300">
            Four answers are enough to start: which Enphase system to read, when
            it was installed, and where it is. Everything below that only sharpens
            the Performance Ratio and can wait.
          </p>
        )}
      </div>

      {justCreated && (
        <div className="rounded-xl border border-emerald-500/40 bg-emerald-500/10 p-5">
          <div className="flex gap-3">
            <span className="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-emerald-500/20 text-emerald-300">
              <CheckIcon />
            </span>
            <div>
              <p className="text-sm font-medium text-white">System registered</p>
              <p className="mt-1 text-sm leading-relaxed text-gray-300">
                The daily poll will now pick up yesterday on its own. To see
                comparisons today, backfill your history first - it walks from
                your install date to yesterday.
              </p>
              <Button
                className="mt-4"
                onClick={() => void status.startBackfill()}
                disabled={status.starting || status.data?.backfill.running}
              >
                {status.starting && <SpinnerIcon className="h-4 w-4" />}
                {status.data?.backfill.running
                  ? "Backfill running"
                  : "Start backfill"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {!isNew && status.data && (
        <SystemStatus
          status={status.data}
          controller={status}
          onGoToSetup={() => undefined}
          variant="full"
        />
      )}

      <form onSubmit={handleSubmit} noValidate={false}>
        <Group
          title="Enphase connection"
          description="Which system to read, and how far back to read it. API credentials stay in your .env file and are never entered here."
        >
          <Field
            label="Enphase System ID"
            name="enphase_system_id"
            defaultValue={data?.enphase_system_id}
            required={isNew}
            readOnly={!isNew}
            placeholder="1234567"
            hint={
              isNew
                ? "The numeric ID from your Enlighten system URL, also shown in the Enphase developer portal."
                : "Fixed after registration - changing it would orphan every stored interval."
            }
          />
          <Field
            label="Install date"
            name="install_date"
            type="date"
            defaultValue={data?.install_date}
            required
            hint="Backfill starts here. Nothing before this date is fetched."
          />
        </Group>

        <Group
          title="Where the array is"
          description="Irradiance is fetched for a single point on the globe and every Performance Ratio is measured against it. A rough rooftop coordinate is fine; a missing one silently puts your array in the Gulf of Guinea."
        >
          <Field
            label="Latitude"
            name="latitude"
            type="number"
            step="any"
            min={-90}
            max={90}
            defaultValue={data?.latitude}
            required
            placeholder="45.5017"
            hint="Decimal degrees. Positive north, negative south."
          />
          <Field
            label="Longitude"
            name="longitude"
            type="number"
            step="any"
            min={-180}
            max={180}
            defaultValue={data?.longitude}
            required
            placeholder="-73.5673"
            hint="Decimal degrees. Positive east, negative west."
          />
          <Field
            label="Location name"
            name="location"
            defaultValue={data?.location}
            placeholder="Montreal, QC"
            hint="Only a label for your own reference."
          />
          <Field
            label="Irradiance source"
            name="irradiance_source_display"
            defaultValue={effectiveSource.toUpperCase()}
            readOnly
            hint={
              status.data?.weather_normalized
                ? "NASA POWER returns real per-day irradiance, so Performance Ratio is genuinely weather-adjusted. Set by IRRADIANCE_SOURCE in .env."
                : "NREL returns a 30-year typical year and ignores the date, so Performance Ratio here is not weather-adjusted. Set IRRADIANCE_SOURCE=nasa in .env and restart the API to change it."
            }
          />
        </Group>

        <Group
          title="Array specification"
          description="Optional. These sharpen the expected-production model behind Performance Ratio and the degradation estimate. Sensible defaults are used where you leave a field blank."
        >
          <Field
            label="System name"
            name="name"
            defaultValue={data?.name}
            placeholder="Roof array"
            hint="Shown nowhere yet; kept for your own records."
          />
          <Field
            label="System size (kW)"
            name="system_size_kw"
            type="number"
            step="any"
            min={0}
            defaultValue={data?.system_size_kw}
            placeholder="9.6"
            hint="Nameplate DC capacity."
          />
          <Field
            label="Panel count"
            name="panel_count"
            type="number"
            step="1"
            min={1}
            defaultValue={data?.panel_count}
            placeholder="24"
          />
          <Field
            label="Panel wattage (W)"
            name="panel_wattage_w"
            type="number"
            step="1"
            min={1}
            defaultValue={data?.panel_wattage_w}
            placeholder="400"
          />
          <Field
            label="Tilt (degrees)"
            name="tilt_angle_deg"
            type="number"
            step="any"
            min={0}
            max={90}
            defaultValue={data?.tilt_angle_deg}
            placeholder="30"
            hint="Roof pitch from horizontal. Treated as 30 when blank."
          />
          <Field
            label="Azimuth (degrees)"
            name="azimuth_deg"
            type="number"
            step="any"
            min={0}
            max={360}
            defaultValue={data?.azimuth_deg}
            placeholder="180"
            hint="Compass direction the panels face; 180 is due south. Treated as 180 when blank."
          />
          <Field
            label="Degradation rate (%/yr)"
            name="degradation_rate"
            type="number"
            step="any"
            min={0}
            max={10}
            defaultValue={data?.degradation_rate}
            placeholder="0.5"
            hint="Expected annual loss, used to draw the expected-PR line. Most panel warranties assume 0.5."
          />
        </Group>

        {saveError && (
          <p role="alert" className="mt-8 text-sm text-red-300">
            {saveError}
          </p>
        )}

        <div className="mt-8 flex items-center gap-3">
          <Button type="submit" disabled={saving}>
            {saving && <SpinnerIcon className="h-4 w-4" />}
            {isNew ? "Register system" : "Save changes"}
          </Button>
          {!isNew && !saving && !saveError && (
            <span className="text-xs text-gray-400">
              Changes to location or geometry only affect days polled from now on.
              Rebuild summaries to apply them to history.
            </span>
          )}
        </div>
      </form>
    </div>
  );
}
