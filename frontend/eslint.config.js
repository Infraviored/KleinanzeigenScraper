import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist', 'node_modules']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
    },
    rules: {
      // Guardrail 1: Prevent god-files from expanding further
      'max-lines': [
        'warn',
        {
          max: 400,
          skipBlankLines: true,
          skipComments: true,
        },
      ],

      // Guardrail 2: Cyclomatic complexity warning
      'complexity': ['warn', { max: 20 }],

      // React hooks relaxation for synchronization effects
      'react-hooks/set-state-in-effect': 'warn',

      // Guardrail 3: Banned arbitrary pixel fonts and hallucinated Tailwind classes
      'no-restricted-syntax': [
        'error',
        {
          selector: 'JSXAttribute[name.name="className"] > Literal[value=/text-\\[[0-9]+px\\]/]',
          message:
            'Hardcoded pixel text size (text-[...px]) used. Use the @theme type scale tokens (text-2xs, text-xs, text-sm, text-base, text-lg, text-xl) instead.',
        },
        {
          selector: 'JSXAttribute[name.name="className"] TemplateElement[value.raw=/text-\\[[0-9]+px\\]/]',
          message:
            'Hardcoded pixel text size (text-[...px]) used. Use the @theme type scale tokens instead.',
        },
        // Tailwind's palette only has the shades 50 and 100-900 in hundreds,
        // plus 950. Any other number is a class Tailwind cannot resolve, and an
        // unresolvable class is dropped in silence -- which is how twelve
        // borders and labels rendered unstyled for weeks behind a green build.
        // Matching the shape of the mistake rather than the two instances of it
        // that happened to be found.
        {
          selector: String.raw`JSXAttribute[name.name="className"] > Literal[value=/\b(?:bg|text|border|ring|from|via|to|fill|stroke|divide|outline|shadow|accent|caret|decoration|placeholder)-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-(?!50\b|100\b|200\b|300\b|400\b|500\b|600\b|700\b|800\b|900\b|950\b)\d+/]`,
          message:
            'Tailwind has no such shade, so this class is silently discarded and the element renders unstyled. Valid shades are 50, 100-900 in hundreds, and 950 - or use a token from index.css.',
        },
        {
          selector: String.raw`JSXAttribute[name.name="className"] TemplateElement[value.raw=/\b(?:bg|text|border|ring|from|via|to|fill|stroke|divide|outline|shadow|accent|caret|decoration|placeholder)-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-(?!50\b|100\b|200\b|300\b|400\b|500\b|600\b|700\b|800\b|900\b|950\b)\d+/]`,
          message:
            'Tailwind has no such shade, so this class is silently discarded and the element renders unstyled. Valid shades are 50, 100-900 in hundreds, and 950 - or use a token from index.css.',
        },
        {
          selector: 'JSXElement > JSXText[value=/[a-zA-Z]{4,}/]',
          message:
            'Potential untranslated copy in JSX. Use useTranslation hook (t(...)) instead of hardcoded text literals.',
        },
      ],
    },
  },
  {
    files: ['**/i18n/**'],
    rules: {
      'max-lines': 'off',
    },
  },
])
