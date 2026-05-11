(function bootstrapLinkedInScraper() {
  const sectionMatchers = [
    { key: "experience", labels: ["experience"] },
    { key: "education", labels: ["education"] },
    { key: "certifications", labels: ["licenses & certifications", "licenses and certifications", "certifications"] },
    { key: "projects", labels: ["projects"] },
    { key: "skills", labels: ["skills"] },
    { key: "honors_awards", labels: ["honors & awards", "honors and awards"] },
  ];

  function normalizeText(value) {
    return String(value ?? "")
      .replace(/[\u200b\u200c\u200d\u200e\u200f\u00ad\ufeff\u034f\u115f\u1160\u17b4\u17b5\u3164]/g, "")
      .replace(/\s+/g, " ")
      .trim();
  }

  function getHeadingText(containerElement) {
    // LinkedIn markup changes frequently; headings are not always direct h2/h3.
    const heading = containerElement.querySelector(
      'h1,h2,h3,[role="heading"],header h1,header h2,header h3'
    );
    return normalizeText(heading?.innerText ?? "");
  }

  function collectSectionRows(containerElement) {
    const rows = [];
    // Prefer list-based extraction (LinkedIn uses many <li> blocks).
    const listItems = containerElement.querySelectorAll("li");
    for (const listItem of listItems) {
      const text = normalizeText(listItem.innerText);
      if (text && text.length > 2 && !rows.includes(text)) {
        rows.push(text);
      }
      if (rows.length >= 200) {
        break;
      }
    }
    // Fallback: some sections are rendered without <li> at capture time.
    if (rows.length === 0) {
      const blocks = containerElement.querySelectorAll("p,span");
      for (const block of blocks) {
        const text = normalizeText(block.innerText);
        if (text && text.length > 2 && text.length <= 200 && !rows.includes(text)) {
          rows.push(text);
        }
        if (rows.length >= 200) {
          break;
        }
      }
    }
    return rows;
  }

  function findContainerByLabel(label) {
    const normalizedLabel = normalizeText(label).toLowerCase();
    const root = document.querySelector("main") ?? document;

    // 1) Best case: section id matches (LinkedIn often uses ids like "experience", "education", etc.).
    const byId = root.querySelector(`#${CSS.escape(normalizedLabel)}`);
    if (byId) {
      return byId.closest("section,div,article") ?? byId;
    }

    // 2) Look for a container with a matching visible heading text.
    const containers = root.querySelectorAll("section,article,div");
    for (const container of containers) {
      const headingText = getHeadingText(container).toLowerCase();
      if (headingText && headingText.includes(normalizedLabel)) {
        return container;
      }
    }

    // 3) Look for any "heading-like" element containing the label and bubble up.
    const headingLike = root.querySelectorAll('h1,h2,h3,[role="heading"]');
    for (const node of headingLike) {
      const text = normalizeText(node.innerText).toLowerCase();
      if (text && text.includes(normalizedLabel)) {
        return node.closest("section,article,div") ?? null;
      }
    }

    return null;
  }

  function clickExpandableButtons(root) {
    const candidates = root.querySelectorAll("button");
    for (const el of candidates) {
      if (el.disabled) {
        continue;
      }
      const label = normalizeText(
        el.getAttribute("aria-label") ?? el.getAttribute("title") ?? el.innerText ?? ""
      ).toLowerCase();
      if (!label) {
        continue;
      }
      // Avoid nav-style controls that can jump across profile tabs/sections.
      if (
        label.includes("follow") ||
        label.includes("message") ||
        label.includes("connect") ||
        label.includes("open to") ||
        label.includes("view all") ||
        label.includes("activity")
      ) {
        continue;
      }
      const expanded = el.getAttribute("aria-expanded");
      if (expanded === "true") {
        continue;
      }
      // Keep matching specific to content expansion actions only.
      if (
        label.includes("see more") ||
        label.includes("show more") ||
        label.includes("show all") ||
        label.includes("expand")
      ) {
        try {
          el.click();
        } catch (_error) {
          // Ignore click failures; best-effort expansion.
        }
      }
    }
  }

  async function ensureProfileContentLoaded() {
    // LinkedIn lazily renders sections as you scroll. Best-effort scrolling helps surface them.
    const root = document.querySelector("main") ?? document.documentElement;
    clickExpandableButtons(root);
    const steps = 8;
    for (let i = 0; i < steps; i += 1) {
      window.scrollTo(0, document.body.scrollHeight);
      await new Promise((resolve) => setTimeout(resolve, 400));
      clickExpandableButtons(root);
    }
    window.scrollTo(0, 0);
  }

  function extractProfileName() {
    // LinkedIn injects invisible characters and changes their markup frequently.
    // Try progressively broader selectors; return the first non-empty result.
    const selectors = [
      // Current LinkedIn markup (2025+)
      "h1.text-heading-xlarge",
      ".text-heading-xlarge",
      // Older LinkedIn class names kept as fallbacks
      ".pv-text-details__left-panel h1",
      ".ph5 h1",
      // Semantic fallbacks — broad but reliable when classes change
      "main h1",
      "article h1",
      "h1",
    ];
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (!el) {
        continue;
      }
      // Use textContent as well as innerText: innerText returns "" for hidden
      // elements, textContent still contains the raw text.
      const text = normalizeText(el.innerText || el.textContent || "");
      if (text) {
        return text;
      }
    }

    // Final fallback: LinkedIn page titles are always "Full Name | LinkedIn"
    // or "Full Name - Headline | LinkedIn". This is set server-side and never
    // depends on CSS class names.
    const titleText = normalizeText(document.title ?? "");
    if (titleText) {
      const pipeIndex = titleText.indexOf("|");
      const dashIndex = titleText.indexOf(" - ");
      const cutAt = Math.min(
        pipeIndex >= 0 ? pipeIndex : Infinity,
        dashIndex >= 0 ? dashIndex : Infinity
      );
      if (Number.isFinite(cutAt)) {
        const nameFromTitle = normalizeText(titleText.slice(0, cutAt));
        if (nameFromTitle) {
          return nameFromTitle;
        }
      }
    }

    return "";
  }

  function extractLinkedInProfile() {
    const sections = {};
    for (const matcher of sectionMatchers) {
      const matchedSection = matcher.labels
        .map((label) => findContainerByLabel(label))
        .find(Boolean);
      sections[matcher.key] = matchedSection ? collectSectionRows(matchedSection) : [];
    }

    return {
      profileName: extractProfileName(),
      profileUrl: window.location.href,
      sections,
    };
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type === "GET_VIEWPORT_SIZE") {
      sendResponse({
        ok: true,
        data: {
          width: window.innerWidth,
          height: window.innerHeight,
          url: window.location.href,
        },
      });
      return;
    }
    if (message?.type !== "SCRAPE_PROFILE") {
      return;
    }
    (async () => {
      try {
        await ensureProfileContentLoaded();
        const payload = extractLinkedInProfile();
        sendResponse({ ok: true, data: payload });
      } catch (error) {
        sendResponse({ ok: false, error: error?.message ?? "Unknown scrape error." });
      }
    })();
    return true; // keep the message channel open for async response
  });
})();
