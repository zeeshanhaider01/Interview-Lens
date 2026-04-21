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
    return String(value ?? "").replace(/\s+/g, " ").trim();
  }

  function getHeadingText(sectionElement) {
    const heading = sectionElement.querySelector("h1,h2,h3");
    return normalizeText(heading?.innerText ?? "");
  }

  function collectSectionRows(sectionElement) {
    const rows = [];
    const listItems = sectionElement.querySelectorAll("li");
    for (const listItem of listItems) {
      const text = normalizeText(listItem.innerText);
      if (text && text.length > 2 && !rows.includes(text)) {
        rows.push(text);
      }
      if (rows.length >= 200) {
        break;
      }
    }
    return rows;
  }

  function findSectionByLabel(label) {
    const sections = document.querySelectorAll("section");
    const normalizedLabel = normalizeText(label).toLowerCase();
    for (const section of sections) {
      const headingText = getHeadingText(section).toLowerCase();
      if (headingText.includes(normalizedLabel)) {
        return section;
      }
    }
    return null;
  }

  function extractLinkedInProfile() {
    const sections = {};
    for (const matcher of sectionMatchers) {
      const matchedSection = matcher.labels
        .map((label) => findSectionByLabel(label))
        .find(Boolean);
      sections[matcher.key] = matchedSection ? collectSectionRows(matchedSection) : [];
    }

    return {
      profileName: normalizeText(document.querySelector("h1")?.innerText ?? ""),
      profileUrl: window.location.href,
      sections,
    };
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type !== "SCRAPE_PROFILE") {
      return;
    }
    try {
      const payload = extractLinkedInProfile();
      sendResponse({ ok: true, data: payload });
    } catch (error) {
      sendResponse({ ok: false, error: error.message });
    }
    return true;
  });
})();
