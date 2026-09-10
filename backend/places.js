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

// Two spellings of every place, because people type both.
//
// `spelled` writes umlauts out (München -> muenchen) and `plain` drops them
// (muenchen -> munchen). A query is folded both ways and matched against both
// indexes, so "München", "Muenchen" and "Munchen" all land on the same town
// exactly, instead of being left to a similarity score. That was not academic:
// "Nurnberg" scored 0.857 against *Bernburg* and only 0.80 against Nürnberg, so
// the wrong city ranked first; "koln" and "furth" scored below the threshold and
// returned nothing at all.
//
// The qualifier is stripped the same way on both sides. It has to be: the table
// writes "b Trier" and "a d Havel" without dots in 3,117 of its rows, while a
// person types "bei Trier" and "an der Havel". Folding only the spelled-out
// words left the two forms unable to meet, so those places could not be found
// by their own names.
const QUALIFIER_WORDS =
  /\b(a|b|i|d|am|an|auf|bei|beim|im|in|ob|unter|vor|der|den|dem|die|das)\b\.?/g;

function normalise(text) {
  return String(text).trim().toLowerCase()
    .replace(/\./g, ' ')
    .replace(QUALIFIER_WORDS, ' ')
    .replace(/[^a-zäöüß0-9 ]+/g, ' ')
    .split(/\s+/).filter(Boolean).join(' ');
}

function spelled(text) {
  return normalise(text)
    .replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss');
}

function plain(text) {
  return normalise(text)
    .replace(/ä/g, 'a').replace(/ö/g, 'o').replace(/ü/g, 'u').replace(/ß/g, 'ss');
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
        _name: spelled(name),
        _full: spelled(town),
        _namePlain: plain(name),
        _fullPlain: plain(town),
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

  const needle = spelled(text);
  const needlePlain = plain(text);
  if (!needle) return [];

  const scored = [];
  for (const place of places) {
    const forms = [place._name, place._full];
    const formsPlain = [place._namePlain, place._fullPlain];

    let rank;
    if (forms.some(f => f.startsWith(needle)) ||
        formsPlain.some(f => f.startsWith(needlePlain))) rank = 0;
    else if (forms.some(f => f.includes(needle)) ||
             formsPlain.some(f => f.includes(needlePlain))) rank = 1;
    else {
      // Only genuine typos reach this. Both spellings match exactly now, so the
      // threshold can be strict rather than loose enough to bridge them — at
      // 0.72 it admitted "Melle" for "Celle" and every other rhyme.
      const ratio = Math.max(
        similarity(needle, place._name), similarity(needlePlain, place._namePlain)
      );
      if (ratio < 0.84) continue;
      rank = 3 - ratio;
    }
    scored.push([rank, place._name.length, place.name, place]);
  }

  scored.sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2].localeCompare(b[2]));
  return scored.slice(0, limit).map(row => row[3]);
}

load();

module.exports = { suggest, reload: load, count: () => places.length };
