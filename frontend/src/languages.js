export const SUPPORTED_LANGUAGES = {
  zh: { name: "中文", englishName: "Chinese" },
  en: { name: "English", englishName: "English" },
  ja: { name: "日本語", englishName: "Japanese" },
  ko: { name: "한국어", englishName: "Korean" },
  ru: { name: "Русский", englishName: "Russian" },
};

export function languageLabel(code) {
  return SUPPORTED_LANGUAGES[code]?.name || code?.toUpperCase() || "未知";
}
