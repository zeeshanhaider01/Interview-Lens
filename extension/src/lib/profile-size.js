import { SECTION_KEYS } from "./constants.js";

const PROFILE_SIZE_LIMITS = {
  WARN_TOKENS: 4000,
  BLOCK_TOKENS: 7000,
};

const PROFILE_SIZE_LEVELS = {
  OK: "ok",
  WARN: "warn",
  BLOCK: "block",
};

const SECTION_LABELS = {
  experience: "Experience",
  education: "Education",
  certifications: "Certifications",
  projects: "Projects",
  skills: "Skills",
  honors_awards: "Honors & Awards",
};

function estimateTokensFromChars(charCount) {
  return Math.max(0, Math.ceil(charCount / 4));
}

function sectionCharCount(sections, key) {
  const values = sections?.[key];
  if (!Array.isArray(values)) {
    return 0;
  }
  return values.reduce((sum, item) => sum + String(item ?? "").length, 0);
}

function hasAnySectionContent(sections) {
  return SECTION_KEYS.some((key) => sectionCharCount(sections, key) > 0);
}

function formatSectionLabel(key) {
  return SECTION_LABELS[key] || key;
}

function estimateProfileSize(sections) {
  const chars = SECTION_KEYS.reduce((sum, key) => sum + sectionCharCount(sections, key), 0);
  const estimatedTokens = estimateTokensFromChars(chars);
  const blockTokens = PROFILE_SIZE_LIMITS.BLOCK_TOKENS;
  const percent =
    blockTokens > 0 ? Math.min(100, Math.round((estimatedTokens / blockTokens) * 100)) : 0;

  let level = PROFILE_SIZE_LEVELS.OK;
  let badgeLabel = "OK";
  let hint = "Profile size is within the recommended range for AI prep.";

  if (estimatedTokens >= PROFILE_SIZE_LIMITS.BLOCK_TOKENS) {
    level = PROFILE_SIZE_LEVELS.BLOCK;
    badgeLabel = "TOO LARGE";
    hint = "Profile is too large. Shorten Experience or Skills before sending.";
  } else if (estimatedTokens >= PROFILE_SIZE_LIMITS.WARN_TOKENS) {
    level = PROFILE_SIZE_LEVELS.WARN;
    badgeLabel = "LARGE";
    hint = "Large profile — consider shortening Experience or Skills.";
  }

  const breakdown = SECTION_KEYS.map((key) => {
    const sectionChars = sectionCharCount(sections, key);
    return {
      key,
      label: formatSectionLabel(key),
      chars: sectionChars,
      estimatedTokens: estimateTokensFromChars(sectionChars),
    };
  }).filter((row) => row.chars > 0);

  return {
    chars,
    estimatedTokens,
    percent,
    level,
    badgeLabel,
    hint,
    breakdown,
    hasContent: hasAnySectionContent(sections),
    submitAllowed: estimatedTokens < PROFILE_SIZE_LIMITS.BLOCK_TOKENS,
  };
}

export {
  PROFILE_SIZE_LEVELS,
  PROFILE_SIZE_LIMITS,
  estimateProfileSize,
  estimateTokensFromChars,
};
