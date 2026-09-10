// Place lookup for the route corridor's From/To fields.
//
// This runs in Node rather than calling the Python gazetteer because it answers
// on every keystroke: starting an interpreter per character would make the field
// feel broken no matter how good the matching was. The table is ~18,000 rows and
// is read once at startup.
//
// The ranking is what makes it usable. A prefix of the name beats a match in the
// middle of it, which beats a near-miss, so typing "Landsberg" puts Landsberg
// a. Lech first and still offers the one near Halle — the person is the only one
// who knows which they meant, and the point of the list is to let them say so
// instead of being told afterwards that the name was ambiguous.

const fs = require('fs');
const path = require('path');

const TABLE_PATH = path.join(
  __dirname, '..', 'scraper', 'reference', 'place_centroids.csv'
);

// Umlauts spelled out, "am"/"a." collapsed, punctuation dropped — so that
// "Landsberg am Lech", "landsberg a. lech" and "Muenchen" all land on the form
// the table is indexed by.
function fold(text) {
  let s = String(text).trim().toLowerCase()
    .replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss');
  s = s.replace(/\s(am|an|bei|im|a\.|b\.|i\.)\s/g, ' ').replace(/\s(a|b|i)\.\s*/g, ' ');
  return s.replace(/[^a-z0-9 ]+/g, ' ').split(/\s+/).filter(Boolean).join(' ');
}

function parseCsvLine(line) {
  const fields = [];
  let current = '';
  let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (quoted) {
      if (ch === '"' && line[i + 1] === '"') { current += '"'; i++; }
      else if (ch === '"') quoted = false;
      else current += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ',') { fields.push(current); current = ''; }
    else current += ch;
  }
  fields.push(current);
  return fields;
}

let places = [];

function load() {
  try {
    const text = fs.readFileSync(TABLE_PATH, 'utf-8');
    const lines = text.split('\n').slice(1);
    places = [];
    for (const line of lines) {
      if (!line.trim()) continue;
      const [name, qualifier, state, postalCode, lat, lon] = parseCsvLine(line);
      if (!name || !postalCode) continue;
      const town = qualifier ? `${name} ${qualifier}` : name;
      places.push({
        name,
        qualifier,
        state,
        postal_code: postalCode,
        lat: Number(lat),
        lon: Number(lon),
        label: `${postalCode} ${town}, ${state}`,
        _name: fold(name),
        _full: fold(town),
      });
    }
    console.log(`Loaded ${places.length} places for route lookup`);
  } catch (error) {
    console.error('Could not load the place table:', error.message);
    places = [];
  }
}

// Similarity for near-misses, so a typo still finds the town. Dice coefficient
// over character bigrams: cheap, and unlike a prefix test it survives a wrong
// letter in the middle of the word.
function similarity(a, b) {
  if (a === b) return 1;
  if (a.length < 2 || b.length < 2) return 0;
  const bigrams = new Map();
  for (let i = 0; i < a.length - 1; i++) {
    const pair = a.slice(i, i + 2);
    bigrams.set(pair, (bigrams.get(pair) || 0) + 1);
  }
  let hits = 0;
  for (let i = 0; i < b.length - 1; i++) {
    const pair = b.slice(i, i + 2);
    const count = bigrams.get(pair) || 0;
    if (count > 0) { bigrams.set(pair, count - 1); hits++; }
  }
  return (2 * hits) / (a.length + b.length - 2);
}

function suggest(query, limit = 8) {
  const text = String(query || '').trim();
  if (text.length < 2) return [];

  if (/^\d{2,5}/.test(text)) {
    const digits = text.slice(0, 5);
    const exact = places.filter(p => p.postal_code.startsWith(digits));
    if (exact.length) return exact.slice(0, limit);
  }

  const needle = fold(text);
  if (!needle) return [];

  const scored = [];
  for (const place of places) {
    let rank;
    if (place._name.startsWith(needle) || place._full.startsWith(needle)) rank = 0;
    else if (place._name.includes(needle) || place._full.includes(needle)) rank = 1;
    else {
      const ratio = similarity(needle, place._name);
      if (ratio < 0.72) continue;
      rank = 3 - ratio;
    }
    scored.push([rank, place._name.length, place.name, place]);
  }

  scored.sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2].localeCompare(b[2]));
  return scored.slice(0, limit).map(row => row[3]);
}

load();

module.exports = { suggest, reload: load, count: () => places.length };
