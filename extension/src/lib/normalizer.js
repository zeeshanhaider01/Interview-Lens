import { SECTION_KEYS } from "./constants.js";

function sanitizeSectionValues(values) {
  if (!Array.isArray(values)) {
    return [];
  }
  return values
    .map((item) => String(item ?? "").replace(/\s+/g, " ").trim())
    .filter(Boolean)
    .slice(0, 200);
}

function normalizeCapture(rawCapture) {
  const extracted = {};
  for (const key of SECTION_KEYS) {
    extracted[key] = sanitizeSectionValues(rawCapture?.sections?.[key] ?? []);
  }

  const sectionCounts = Object.fromEntries(
    Object.entries(extracted).map(([key, values]) => [key, values.length]),
  );
  return {
    source: "LINKEDIN",
    source_url: rawCapture?.profileUrl ?? "",
    extracted_sections: extracted,
    confidence_flags: {
      parser_version: "v1",
      section_counts: sectionCounts,
      extraction_mode: "dom-heading-match",
    },
    metadata: {
      captured_at: new Date().toISOString(),
      profile_name: rawCapture?.profileName ?? "",
    },
  };
}

export { normalizeCapture };
