import { SCIENTIST_LOADING_CATALOG } from './scientist-resonance-loading-catalog.js';

function hasLoadingCopy(entry) {
  return Boolean(entry && (entry.loading_copy_zh || entry.loading_copy_en));
}

export function getLoadingCopyForLanguage(entry, language) {
  const normalized = String(language || '').toLowerCase();
  if (normalized.startsWith('zh')) {
    return entry?.loading_copy_zh || entry?.loading_copy_en || '';
  }
  return entry?.loading_copy_en || entry?.loading_copy_zh || '';
}

function toLoadingEntry(card) {
  if (!card || !hasLoadingCopy(card)) {
    return null;
  }
  return {
    slug: card.slug,
    name: card.name,
    loading_copy_zh: card.loading_copy_zh || '',
    loading_copy_en: card.loading_copy_en || '',
  };
}

export function buildScientistLoadingSequence(
  payload,
  catalog = SCIENTIST_LOADING_CATALOG,
) {
  const relevant = [];
  const seen = new Set();

  const push = (entry) => {
    if (!entry || seen.has(entry.slug) || !hasLoadingCopy(entry)) {
      return;
    }
    seen.add(entry.slug);
    relevant.push(entry);
  };

  push(toLoadingEntry(payload?.long_term?.primary));
  for (const card of payload?.long_term?.secondary || []) {
    push(toLoadingEntry(card));
  }
  push(toLoadingEntry(payload?.recent_state));

  const others = [];
  for (const item of catalog) {
    if (!item || seen.has(item.slug) || !hasLoadingCopy(item)) {
      continue;
    }
    seen.add(item.slug);
    others.push({
      slug: item.slug,
      name: item.name,
      loading_copy_zh: item.loading_copy_zh || '',
      loading_copy_en: item.loading_copy_en || '',
    });
  }

  return [...relevant, ...others];
}
