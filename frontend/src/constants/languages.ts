/** Human-readable labels for the language codes used across project language pickers. */
export const LANG_LABELS: Record<string, string> = {
  en: "English", te: "Telugu", hi: "Hindi", ta: "Tamil", kn: "Kannada",
  ml: "Malayalam", bn: "Bengali", mr: "Marathi", gu: "Gujarati", pa: "Punjabi",
  fr: "French", de: "German", es: "Spanish", ja: "Japanese",
  ko: "Korean", "zh-CN": "Chinese",
};

export const languageLabel = (code: string): string => LANG_LABELS[code] || code;
