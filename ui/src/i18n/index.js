function normalizeMessages(module) {
  return module.default || module;
}

function deepMerge(base, override) {
  if (Array.isArray(base) || Array.isArray(override)) {
    return override;
  }

  const merged = { ...base };
  for (const [key, value] of Object.entries(override || {})) {
    if (
      value &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      base &&
      typeof base[key] === "object" &&
      !Array.isArray(base[key])
    ) {
      merged[key] = deepMerge(base[key], value);
    } else {
      merged[key] = value;
    }
  }
  return merged;
}

export async function loadLanguage(lang) {
  const englishModule = await import(
    /* webpackChunkName: "lang-en" */ `../../public/i18n/en/translation.json`
  );
  const englishMessages = normalizeMessages(englishModule);

  try {
    const languageModule = await import(
      /* webpackChunkName: "lang-[request]" */ `../../public/i18n/${lang}/translation.json`
    );
    const languageMessages = normalizeMessages(languageModule);
    return {
      default: deepMerge(englishMessages, languageMessages),
    };
  } catch (error) {
    console.warn(
      `Cannot import ${lang} language messages, falling back to English.`,
      error
    );
    return { default: englishMessages };
  }
}
