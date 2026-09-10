/* eslint-disable react-hooks/set-state-in-effect */
import { useState, useEffect, useRef, useId } from 'react'
import { Input } from './ui/Input'

export type Place = {
  label: string
  name: string
  qualifier: string
  state: string
  postal_code: string
  lat: number
  lon: number
}

type Props = {
  label: string
  placeholder: string
  value: Place | null
  onChange: (place: Place | null) => void
  emptyHint: string
}

/**
 * A place field that offers what it knows instead of judging what was typed.
 *
 * The previous version took free text and resolved it when the form was
 * submitted, which meant "Landsberg am Lech" came back as *Could not place
 * 'Landsberg am Lech'. Give a postal code, or "Ort, Bundesland"* — after the
 * fact, in the interface's vocabulary rather than the user's, and asking them to
 * solve an ambiguity they never saw. There are two Landsbergs; only the person
 * typing knows which one they meant.
 *
 * So the list is the answer. Every entry names its postal code and state, both
 * Landsbergs appear, and picking one leaves nothing left to resolve. A place is
 * chosen, not parsed.
 */
export default function PlaceInput({ label, placeholder, value, onChange, emptyHint }: Props) {
  const [text, setText] = useState(value ? value.label : '')
  const [matches, setMatches] = useState<Place[]>([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const [searching, setSearching] = useState(false)
  const listId = useId()
  const containerRef = useRef<HTMLDivElement>(null)
  // Suppresses the lookup that a selection's own text change would otherwise
  // trigger — picking a place should close the list, not repopulate it.
  const skipNextLookup = useRef(false)
  const listRef = useRef<HTMLUListElement>(null)

  // The field follows its value. Clearing it from outside — which is what the
  // form does after planning a corridor — has to clear what is on screen too,
  // or the input keeps showing a place the application no longer holds.
  useEffect(() => {
    if (value === null && text !== '') {
      skipNextLookup.current = true
      setText('')
      setMatches([])
      setOpen(false)
    }
    // Only reacting to the value going away; typing is handled below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])

  useEffect(() => {
    if (skipNextLookup.current) {
      skipNextLookup.current = false
      return
    }
    if (text.trim().length < 2) {
      setMatches([])
      setSearching(false)
      return
    }

    let cancelled = false
    setSearching(true)
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`/api/places/suggest?q=${encodeURIComponent(text)}`)
        if (!res.ok || cancelled) return
        const data = await res.json()
        if (cancelled) return
        setMatches(data.places || [])
        setActive(0)
        setOpen(true)
      } catch {
        if (!cancelled) setMatches([])
      } finally {
        if (!cancelled) setSearching(false)
      }
    }, 180)

    return () => { cancelled = true; clearTimeout(timer) }
  }, [text])

  // Clicking away closes the list without choosing anything.
  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    return () => document.removeEventListener('mousedown', onPointerDown)
  }, [open])

  const choose = (place: Place) => {
    // Only arm the skip if the text is actually about to change. Choosing the
    // suggestion whose label already equals the input leaves React with nothing
    // to re-render, the effect never runs, and the flag would stay armed to
    // swallow the next real keystroke instead.
    skipNextLookup.current = place.label !== text
    setText(place.label)
    setMatches([])
    setOpen(false)
    onChange(place)
  }

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Escape') { setOpen(false); return }
    // Moving on with Tab is leaving this field; a list left floating over the
    // page belongs to a field the user is no longer in.
    if (event.key === 'Tab') { setOpen(false); return }
    if (!open || matches.length === 0) return

    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActive(i => (i + 1) % matches.length)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActive(i => (i - 1 + matches.length) % matches.length)
    } else if (event.key === 'Enter') {
      event.preventDefault()
      choose(matches[active])
    }
  }

  // Keep the highlighted option in view: arrowing past the bottom of a
  // scrollable list otherwise highlights something nobody can see.
  useEffect(() => {
    if (!open) return
    listRef.current?.children[active]?.scrollIntoView({ block: 'nearest' })
  }, [active, open])

  return (
    <div className="space-y-1.5 relative" ref={containerRef}>
      <label htmlFor={`${listId}-input`} className="text-2xs text-slate-500 font-bold uppercase tracking-wider block">
        {label}
      </label>
      <Input
        id={`${listId}-input`}
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && matches.length ? `${listId}-${active}` : undefined}
        autoComplete="off"
        value={text}
        onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
          setText(e.target.value)
          // The typed text no longer describes the chosen place.
          if (value) onChange(null)
        }}
        onFocus={() => { if (matches.length) setOpen(true) }}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
      />

      {value ? (
        <p className="text-2xs text-emerald-400 font-semibold">{value.label}</p>
      ) : text.trim().length >= 2 && !searching && matches.length === 0 ? (
        <p className="text-2xs text-slate-500">{emptyHint}</p>
      ) : null}

      {open && matches.length > 0 && (
        /* Wider than the field it belongs to, and able to grow past it. The
           town name is the thing being chosen, so it gets the line to itself:
           sharing it with the postal code and the state left "Landsberg ..."
           truncated in a 220 px column, hiding the very word being read. */
        <ul
          id={listId}
          ref={listRef}
          role="listbox"
          className="absolute z-30 left-0 top-full mt-1 min-w-full w-max max-w-[min(28rem,80vw)] max-h-72 overflow-y-auto rounded-xl border border-border-subtle bg-slate-950 shadow-2xl py-1"
        >
          {matches.map((place, index) => (
            <li
              key={`${place.postal_code}-${place.name}-${place.qualifier}`}
              id={`${listId}-${index}`}
              role="option"
              aria-selected={index === active}
              onMouseEnter={() => setActive(index)}
              onMouseDown={e => { e.preventDefault(); choose(place) }}
              className={`px-3 py-2 cursor-pointer ${
                index === active ? 'bg-emerald-500/15' : ''
              }`}
            >
              <div className="text-sm text-slate-100 font-semibold leading-snug">
                {place.qualifier ? `${place.name} ${place.qualifier}` : place.name}
              </div>
              <div className="text-2xs text-slate-500 flex items-center gap-2 leading-snug">
                <span className="font-mono tabular-nums">{place.postal_code}</span>
                <span aria-hidden="true">·</span>
                <span>{place.state}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
