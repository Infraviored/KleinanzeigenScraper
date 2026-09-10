import { useState, useEffect, useRef, useCallback } from 'react'
import { Button } from './ui/Button'
import RouteCorridorMap, { type RouteCircle } from './RouteCorridorMap'
import { useTranslation } from '../hooks/useTranslation'

export interface CorridorPreview {
  distance_km: number
  duration_min: number
  radius_km: number
  half_width_km: number
  polyline: [number, number][]
  circles: RouteCircle[]
  unresolved: string[]
}

type Props = {
  /** The search to re-aim along the route. Not needed when redrawing. */
  baseUrl: string
  origin: string
  destination: string
  originName: string
  destinationName: string
  radiusKm: number
  corridorKm: number
  onRadiusChange: (km: number) => void
  onCorridorChange: (km: number) => void
  /** Confirm. Only ever called once the corridor on screen is the one meant. */
  onCommit: () => void
  committing: boolean
  commitLabel: string
  onCancel?: () => void
}

const RADIUS_STEPS = [20, 25, 30, 35, 40, 45, 50, 60]

/**
 * Draws a corridor before it is built.
 *
 * The corridor is a decision with a shape — how far off the road you are
 * willing to turn, and therefore how many searches it takes to cover. The old
 * form asked for two numbers and went straight to fetching listings, so the
 * first sight of the corridor was a list of results from it.
 *
 * Here the route appears as soon as both ends are known, the circles redraw as
 * the sliders move, and nothing is fetched until the shape on screen is the one
 * meant. The same component redraws an existing corridor, because "widen it and
 * look again" is the same question asked a second time.
 */
export default function CorridorPlanner({
  baseUrl, origin, destination, originName, destinationName,
  radiusKm, corridorKm, onRadiusChange, onCorridorChange,
  onCommit, committing, commitLabel, onCancel,
}: Props) {
  const { t } = useTranslation()
  const [preview, setPreview] = useState<CorridorPreview | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const requestId = useRef(0)

  const load = useCallback(async () => {
    if (!baseUrl || !origin || !destination) return
    const mine = ++requestId.current
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/route-searches/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          base_url: baseUrl,
          origin,
          destination,
          radius_km: radiusKm,
          corridor_km: corridorKm,
        }),
      })
      const data = await res.json()
      // A slower earlier request must not overwrite a newer answer.
      if (mine !== requestId.current) return
      if (!res.ok) {
        setError(data.error || t('common.connectionIssueFailed'))
        setPreview(null)
      } else {
        setPreview(data)
      }
    } catch {
      if (mine === requestId.current) setError(t('common.connectionIssueFailed'))
    } finally {
      if (mine === requestId.current) setLoading(false)
    }
  }, [baseUrl, origin, destination, radiusKm, corridorKm, t])

  // Each redraw is a routing request, so the sliders settle before asking.
  useEffect(() => {
    const timer = setTimeout(load, 350)
    return () => clearTimeout(timer)
  }, [load])

  const searches = preview?.circles.length ?? 0

  return (
    <div className="space-y-4">
      <div className="rounded-2xl overflow-hidden border border-border-subtle bg-bg-input/40">
        {preview ? (
          <RouteCorridorMap
            polyline={preview.polyline}
            circles={preview.circles}
            listings={[]}
            selectedListingId={null}
            onSelectListing={() => {}}
            originName={originName}
            destinationName={destinationName}
          />
        ) : (
          <div className="h-[320px] flex items-center justify-center text-center px-6">
            <p className="text-sm text-text-muted">
              {error ? error : loading ? t('corridor.drawing') : t('corridor.awaitingEnds')}
            </p>
          </div>
        )}
      </div>

      {preview && (
        <div className="flex flex-wrap items-baseline gap-x-5 gap-y-1 text-sm">
          <span className="text-text-secondary">
            <span className="font-mono font-bold text-lg text-text-primary">{searches}</span>{' '}
            {t('corridor.searchesNeeded')}
          </span>
          <span className="text-text-muted font-mono text-xs">
            {preview.distance_km} km · {preview.duration_min} min
          </span>
          {loading && <span className="text-text-muted text-xs">{t('corridor.drawing')}</span>}
        </div>
      )}

      {/* Radius first: it is the size of the tool. The corridor is what you then
          ask that tool to cover, and it cannot exceed it. */}
      <div className="space-y-4 rounded-2xl border border-border-subtle bg-bg-input/40 p-4">
        <div className="space-y-2">
          <div className="flex items-baseline justify-between gap-3">
            <label htmlFor="planner-radius" className="text-sm font-semibold text-text-secondary">
              {t('corridor.radiusLabel')}
            </label>
            <span className="font-mono text-sm text-text-primary">{radiusKm} km</span>
          </div>
          <input
            id="planner-radius"
            type="range"
            min={0}
            max={RADIUS_STEPS.length - 1}
            step={1}
            value={Math.max(0, RADIUS_STEPS.indexOf(radiusKm))}
            onChange={e => {
              const next = RADIUS_STEPS[Number(e.target.value)]
              onRadiusChange(next)
              // A corridor at least as wide as the circles cannot be covered at
              // any spacing, so the width follows the radius down.
              if (corridorKm > next - 5) onCorridorChange(next - 5)
            }}
            className="w-full accent-brand-accent"
          />
          <p className="text-2xs text-text-muted">{t('corridor.radiusHint')}</p>
        </div>

        <div className="space-y-2">
          <div className="flex items-baseline justify-between gap-3">
            <label htmlFor="planner-corridor" className="text-sm font-semibold text-text-secondary">
              {t('corridor.widthLabel')}
            </label>
            <span className="font-mono text-sm text-text-primary">± {corridorKm} km</span>
          </div>
          <input
            id="planner-corridor"
            type="range"
            min={5}
            max={radiusKm - 5}
            step={5}
            value={corridorKm}
            onChange={e => onCorridorChange(Number(e.target.value))}
            className="w-full accent-brand-accent"
          />
          <p className="text-2xs text-text-muted">{t('corridor.widthHint')}</p>
        </div>
      </div>

      {preview && preview.unresolved.length > 0 && (
        <p className="text-2xs text-text-muted">
          {t('corridor.unresolved', { places: preview.unresolved.join(', ') })}
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        <Button
          variant="primary"
          onClick={onCommit}
          disabled={committing || !preview || searches === 0}
          className="min-w-[12rem] py-3"
        >
          {committing ? t('corridor.committing') : commitLabel}
        </Button>
        {onCancel && (
          <Button variant="secondary" onClick={onCancel} disabled={committing} className="py-3">
            {t('common.cancel')}
          </Button>
        )}
      </div>
    </div>
  )
}
